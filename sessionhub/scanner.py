"""Incremental indexing of session files into the SQLite index."""
from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone

from . import config, db
from .parse_antigravity import parse_antigravity
from .parse_claude import SessionRecord, load_history_fallback, parse_claude_file


@dataclass
class ScanSummary:
    files_total: int = 0
    files_parsed: int = 0
    files_skipped: int = 0
    sessions_added: int = 0
    sessions_updated: int = 0
    sessions_removed: int = 0
    malformed_lines: int = 0
    duration_ms: int = 0

    def as_dict(self) -> dict:
        return asdict(self)


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _upsert(con: sqlite3.Connection, rec: SessionRecord, summary: ScanSummary) -> None:
    existing = con.execute(
        "SELECT file_path, file_size FROM sessions WHERE id = ?", (rec.id,)
    ).fetchone()
    relocated = False
    if existing and existing["file_path"] != rec.file_path:
        # same uuid in two project dirs: keep the larger/newer file
        if existing["file_size"] > rec.file_size:
            return
        con.execute("DELETE FROM sessions WHERE id = ?", (rec.id,))
        relocated = True

    con.execute(
        """
        INSERT INTO sessions (
            id, tool, title, title_source, description, project_path,
            project_name, started_at, ended_at, models, message_count,
            user_prompt_count, input_tokens, output_tokens,
            cache_creation_tokens, cache_read_tokens, git_branch, cli_version,
            file_path, file_mtime, file_size, malformed_lines,
            is_workspace_latest, last_scanned_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(id) DO UPDATE SET
            title=excluded.title, title_source=excluded.title_source,
            description=excluded.description,
            project_path=excluded.project_path,
            project_name=excluded.project_name,
            started_at=excluded.started_at, ended_at=excluded.ended_at,
            models=excluded.models, message_count=excluded.message_count,
            user_prompt_count=excluded.user_prompt_count,
            input_tokens=excluded.input_tokens,
            output_tokens=excluded.output_tokens,
            cache_creation_tokens=excluded.cache_creation_tokens,
            cache_read_tokens=excluded.cache_read_tokens,
            git_branch=excluded.git_branch, cli_version=excluded.cli_version,
            file_path=excluded.file_path, file_mtime=excluded.file_mtime,
            file_size=excluded.file_size,
            malformed_lines=excluded.malformed_lines,
            is_workspace_latest=excluded.is_workspace_latest,
            last_scanned_at=excluded.last_scanned_at
        """,
        (
            rec.id, rec.tool, rec.title, rec.title_source, rec.description,
            rec.project_path, rec.project_name, rec.started_at, rec.ended_at,
            json.dumps(rec.models) if rec.models else None, rec.message_count,
            rec.user_prompt_count, rec.input_tokens, rec.output_tokens,
            rec.cache_creation_tokens, rec.cache_read_tokens, rec.git_branch,
            rec.cli_version, rec.file_path, rec.file_mtime, rec.file_size,
            rec.malformed_lines, rec.is_workspace_latest, _now_iso(),
        ),
    )
    con.execute("DELETE FROM prompts WHERE session_id = ?", (rec.id,))
    con.executemany(
        "INSERT INTO prompts (session_id, seq, ts, text) VALUES (?,?,?,?)",
        [(rec.id, i, ts, text) for i, (ts, text) in enumerate(rec.prompts)],
    )
    con.execute("DELETE FROM prompts_fts WHERE session_id = ?", (rec.id,))
    con.executemany(
        "INSERT INTO prompts_fts(text, session_id) VALUES (?,?)",
        [(text, rec.id) for _, text in rec.prompts if text],
    )
    if existing or relocated:
        summary.sessions_updated += 1
    else:
        summary.sessions_added += 1


def scan(con: sqlite3.Connection) -> ScanSummary:
    start = time.monotonic()
    summary = ScanSummary()
    stored = {
        row["file_path"]: (row["file_mtime"], row["file_size"])
        for row in con.execute(
            "SELECT file_path, file_mtime, file_size FROM sessions WHERE tool='claude'"
        )
    }
    seen: set[str] = set()
    history_fallback = None

    if config.CLAUDE_PROJECTS.is_dir():
        for project_dir in sorted(config.CLAUDE_PROJECTS.iterdir()):
            if not project_dir.is_dir():
                continue
            for f in project_dir.glob("*.jsonl"):
                summary.files_total += 1
                seen.add(str(f))
                st = f.stat()
                if stored.get(str(f)) == (st.st_mtime, st.st_size):
                    summary.files_skipped += 1
                    continue
                rec = parse_claude_file(f)
                if not rec.title or not rec.project_path:
                    if history_fallback is None:
                        history_fallback = load_history_fallback()
                    project, display = history_fallback.get(rec.id, ("", ""))
                    if not rec.project_path and project:
                        rec.project_path = project
                    if not rec.title and display:
                        rec.title = display[: config.TITLE_MAX]
                        rec.title_source = "history"
                if not rec.title:
                    rec.title = "(untitled session)"
                summary.malformed_lines += rec.malformed_lines
                summary.files_parsed += 1
                _upsert(con, rec, summary)

    for gone in set(stored) - seen:
        row = con.execute(
            "SELECT id FROM sessions WHERE file_path = ?", (gone,)
        ).fetchone()
        if row:
            con.execute("DELETE FROM prompts WHERE session_id = ?", (row["id"],))
            con.execute("DELETE FROM prompts_fts WHERE session_id = ?", (row["id"],))
            con.execute("DELETE FROM sessions WHERE id = ?", (row["id"],))
            summary.sessions_removed += 1

    # Antigravity: one small history file backs everything — rebuild on change
    ag_mtime = (
        str(config.AG_HISTORY.stat().st_mtime) if config.AG_HISTORY.exists() else None
    )
    if ag_mtime and ag_mtime != db.get_meta(con, "ag_history_mtime"):
        con.execute(
            "DELETE FROM prompts WHERE session_id IN "
            "(SELECT id FROM sessions WHERE tool='antigravity')"
        )
        con.execute(
            "DELETE FROM prompts_fts WHERE session_id IN "
            "(SELECT id FROM sessions WHERE tool='antigravity')"
        )
        con.execute("DELETE FROM sessions WHERE tool='antigravity'")
        for rec in parse_antigravity():
            if not rec.title:
                rec.title = "(untitled conversation)"
            summary.files_parsed += 1
            _upsert(con, rec, summary)
        db.set_meta(con, "ag_history_mtime", ag_mtime)

    db.set_meta(con, "last_scan_at", _now_iso())
    con.commit()
    summary.duration_ms = int((time.monotonic() - start) * 1000)
    return summary
