from __future__ import annotations

from pathlib import Path

HOME = Path.home()

CLAUDE_DIR = HOME / ".claude"
CLAUDE_PROJECTS = CLAUDE_DIR / "projects"
CLAUDE_HISTORY = CLAUDE_DIR / "history.jsonl"
CLAUDE_ACTIVE = CLAUDE_DIR / "sessions"

AG_DIR = HOME / ".gemini" / "antigravity-cli"
AG_HISTORY = AG_DIR / "history.jsonl"
AG_CONVERSATIONS = AG_DIR / "conversations"
AG_LAST_CONVERSATIONS = AG_DIR / "cache" / "last_conversations.json"

DATA_DIR = HOME / ".local" / "share" / "session-hub"
INDEX_DB = DATA_DIR / "index.db"

HOST = "127.0.0.1"
PORT = 8788

DESCRIPTION_MAX = 500
PROMPT_MAX = 2000
TITLE_MAX = 60
