"""Streaming parser for Claude Code session JSONL files."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from . import config

SLASH_COMMAND_RE = re.compile(r"^/[\w:-]+\s*$")


@dataclass
class SessionRecord:
    id: str
    tool: str
    file_path: str
    file_mtime: float
    file_size: int
    title: str | None = None
    title_source: str = "none"
    description: str | None = None
    project_path: str | None = None
    started_at: str | None = None
    ended_at: str | None = None
    models: list[str] = field(default_factory=list)
    message_count: int = 0
    user_prompt_count: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_tokens: int = 0
    cache_read_tokens: int = 0
    git_branch: str | None = None
    cli_version: str | None = None
    malformed_lines: int = 0
    is_workspace_latest: int = 0
    prompts: list[tuple[str | None, str]] = field(default_factory=list)

    @property
    def project_name(self) -> str | None:
        return Path(self.project_path).name if self.project_path else None


def extract_text(content) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = [
            b.get("text", "")
            for b in content
            if isinstance(b, dict) and b.get("type") == "text"
        ]
        return "\n".join(p for p in parts if p).strip()
    return ""


def is_real_prompt(text: str) -> bool:
    if not text:
        return False
    if text.startswith("<"):  # <command-name>, <local-command-stdout>, <system-reminder>...
        return False
    if text.startswith("Caveat:"):
        return False
    if SLASH_COMMAND_RE.match(text):  # bare slash commands like /exit, /clear
        return False
    return True


def parse_claude_file(path: Path) -> SessionRecord:
    st = path.stat()
    rec = SessionRecord(
        id=path.stem,
        tool="claude",
        file_path=str(path),
        file_mtime=st.st_mtime,
        file_size=st.st_size,
    )
    models: set[str] = set()

    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except (json.JSONDecodeError, ValueError):
                rec.malformed_lines += 1
                continue
            if not isinstance(entry, dict):
                rec.malformed_lines += 1
                continue

            ts = entry.get("timestamp")
            if isinstance(ts, str):
                rec.started_at = rec.started_at or ts
                rec.ended_at = ts

            etype = entry.get("type")
            # message_count is the raw turn count (incl. sidechains/tool turns);
            # user_prompt_count below is filtered — the two don't reconcile
            if etype == "ai-title":
                title = entry.get("aiTitle")
                if title:
                    rec.title = title
                    rec.title_source = "ai-title"
            elif etype == "user":
                rec.message_count += 1
                rec.project_path = entry.get("cwd") or rec.project_path
                rec.git_branch = entry.get("gitBranch") or rec.git_branch
                rec.cli_version = entry.get("version") or rec.cli_version
                if entry.get("isSidechain"):
                    continue
                message = entry.get("message") or {}
                text = extract_text(message.get("content"))
                if is_real_prompt(text):
                    rec.prompts.append((ts, text[: config.PROMPT_MAX]))
            elif etype == "assistant":
                rec.message_count += 1
                message = entry.get("message") or {}
                model = message.get("model")
                if model and not model.startswith("<"):  # skip "<synthetic>"
                    models.add(model)
                usage = message.get("usage") or {}
                rec.input_tokens += usage.get("input_tokens") or 0
                rec.output_tokens += usage.get("output_tokens") or 0
                rec.cache_creation_tokens += usage.get("cache_creation_input_tokens") or 0
                rec.cache_read_tokens += usage.get("cache_read_input_tokens") or 0

    rec.models = sorted(models)
    rec.user_prompt_count = len(rec.prompts)
    if rec.prompts:
        rec.description = rec.prompts[0][1][: config.DESCRIPTION_MAX]
    if not rec.title and rec.description:
        rec.title = rec.description[: config.TITLE_MAX]
        rec.title_source = "first-prompt"
    return rec


def load_history_fallback() -> dict[str, tuple[str, str]]:
    """Map sessionId -> (project, first display) from ~/.claude/history.jsonl."""
    out: dict[str, tuple[str, str]] = {}
    if not config.CLAUDE_HISTORY.exists():
        return out
    with open(config.CLAUDE_HISTORY, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            try:
                entry = json.loads(line)
            except (json.JSONDecodeError, ValueError):
                continue
            sid = entry.get("sessionId")
            if sid and sid not in out:
                out[sid] = (entry.get("project") or "", entry.get("display") or "")
    return out
