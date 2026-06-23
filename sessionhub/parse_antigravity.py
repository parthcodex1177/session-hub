"""Build session records for Antigravity CLI conversations.

Source of truth is history.jsonl (prompts, timestamps, workspace). The
per-conversation .db files contain undocumented protobuf blobs, so they are
only used best-effort for a step count, mtime, and model extraction.

Model extraction: the first gen_metadata row starts with a length-prefixed
protobuf string that contains the model name (e.g. "gemini-3-flash-a"). We
read it with a 1-byte length prefix heuristic — if the pattern doesn't match
the expected format, we skip rather than misreport.
"""
import json
import re
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone

from . import config
from .parse_claude import SessionRecord


_MODEL_RE = re.compile(rb"gemini[\w\-\.]+")


def _extract_model(con: sqlite3.Connection) -> str | None:
    """Pull the model name from the first gen_metadata protobuf blob."""
    try:
        row = con.execute("SELECT data FROM gen_metadata LIMIT 1").fetchone()
        if not row:
            return None
        raw: bytes = row[0]
        # The model name is a length-prefixed protobuf string. The byte before
        # the model text holds the string length; text is pure ASCII.
        m = _MODEL_RE.search(raw)
        if not m:
            return None
        start = m.start()
        if start == 0:
            return None
        length = raw[start - 1]
        # sanity: extracted span must match the declared length
        if m.end() - start != length:
            return None
        return raw[start : start + length].decode("ascii")
    except (sqlite3.Error, UnicodeDecodeError, IndexError):
        return None


def _iso(unix_ms: float) -> str:
    return datetime.fromtimestamp(unix_ms / 1000, tz=timezone.utc).isoformat()


def parse_antigravity() -> list[SessionRecord]:
    if not config.AG_HISTORY.exists():
        return []

    groups: dict[str, list[dict]] = defaultdict(list)
    with open(config.AG_HISTORY, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            try:
                entry = json.loads(line)
            except (json.JSONDecodeError, ValueError):
                continue
            cid = entry.get("conversationId")
            if cid and isinstance(entry.get("timestamp"), (int, float)):
                groups[cid].append(entry)

    last_map: dict[str, str] = {}
    try:
        with open(config.AG_LAST_CONVERSATIONS, encoding="utf-8") as fh:
            last_map = json.load(fh)
    except (OSError, json.JSONDecodeError, ValueError):
        pass
    if not last_map:
        # cache missing/unreadable: fall back to latest conversation per
        # workspace by last activity, so resume isn't silently dead
        by_workspace: dict[str, tuple[float, str]] = {}
        for cid, entries in groups.items():
            ws = entries[0].get("workspace") or ""
            last_ts = max(e["timestamp"] for e in entries)
            if ws and last_ts > by_workspace.get(ws, (0, ""))[0]:
                by_workspace[ws] = (last_ts, cid)
        last_map = {ws: cid for ws, (_, cid) in by_workspace.items()}
    latest_ids = set(last_map.values())

    records = []
    history_mtime = config.AG_HISTORY.stat().st_mtime
    for cid, entries in groups.items():
        entries.sort(key=lambda e: e["timestamp"])
        first_text = (entries[0].get("display") or "").strip()
        rec = SessionRecord(
            id=cid,
            tool="antigravity",
            # synthetic source path: one history file backs many conversations
            file_path=f"{config.AG_HISTORY}#{cid}",
            file_mtime=history_mtime,
            file_size=0,
            project_path=entries[0].get("workspace"),
            started_at=_iso(entries[0]["timestamp"]),
            ended_at=_iso(entries[-1]["timestamp"]),
            is_workspace_latest=1 if cid in latest_ids else 0,
        )
        rec.prompts = [
            (_iso(e["timestamp"]), (e.get("display") or "")[: config.PROMPT_MAX])
            for e in entries
            if (e.get("display") or "").strip()
        ]
        rec.user_prompt_count = len(rec.prompts)
        rec.message_count = rec.user_prompt_count
        if first_text:
            rec.description = first_text[: config.DESCRIPTION_MAX]
            rec.title = first_text.splitlines()[0][: config.TITLE_MAX]
            rec.title_source = "first-prompt"

        dbf = config.AG_CONVERSATIONS / f"{cid}.db"
        if dbf.exists():
            st = dbf.stat()
            rec.file_path = str(dbf)
            rec.file_mtime = st.st_mtime
            rec.file_size = st.st_size
            db_iso = datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat()
            rec.ended_at = max(rec.ended_at, db_iso)
            try:
                con = sqlite3.connect(f"file:{dbf}?mode=ro&immutable=1", uri=True)
                try:
                    rec.message_count = con.execute(
                        "SELECT count(*) FROM steps"
                    ).fetchone()[0]
                    model = _extract_model(con)
                    if model:
                        rec.models = [model]
                finally:
                    con.close()
            except sqlite3.Error:
                pass  # undocumented schema; keep the prompt-count proxy
        records.append(rec)
    return records
