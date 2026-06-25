"""Detect Claude Code sessions that are running right now."""
from __future__ import annotations

import json
import os

from . import config


def active_sessions() -> dict[str, str]:
    """Return {sessionId: status} for live Claude processes."""
    out: dict[str, str] = {}
    if not config.CLAUDE_ACTIVE.is_dir():
        return out
    for f in config.CLAUDE_ACTIVE.glob("*.json"):
        try:
            with open(f, encoding="utf-8") as fh:
                entry = json.load(fh)
        except (OSError, json.JSONDecodeError, ValueError):
            continue
        pid = entry.get("pid")
        sid = entry.get("sessionId")
        if not pid or not sid:
            continue
        if not os.path.isdir(f"/proc/{pid}"):  # stale pid file
            continue
        out[sid] = entry.get("status") or "running"
    return out
