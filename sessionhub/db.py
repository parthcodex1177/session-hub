import sqlite3

from . import config

SCHEMA_VERSION = "2"

DDL = """
CREATE TABLE IF NOT EXISTS sessions (
  id                     TEXT PRIMARY KEY,
  tool                   TEXT NOT NULL CHECK (tool IN ('claude','antigravity')),
  title                  TEXT,
  title_source           TEXT,
  description            TEXT,
  project_path           TEXT,
  project_name           TEXT,
  started_at             TEXT,
  ended_at               TEXT,
  models                 TEXT,
  message_count          INTEGER NOT NULL DEFAULT 0,
  user_prompt_count      INTEGER NOT NULL DEFAULT 0,
  input_tokens           INTEGER NOT NULL DEFAULT 0,
  output_tokens          INTEGER NOT NULL DEFAULT 0,
  cache_creation_tokens  INTEGER NOT NULL DEFAULT 0,
  cache_read_tokens      INTEGER NOT NULL DEFAULT 0,
  git_branch             TEXT,
  cli_version            TEXT,
  file_path              TEXT NOT NULL UNIQUE,
  file_mtime             REAL NOT NULL,
  file_size              INTEGER NOT NULL,
  malformed_lines        INTEGER NOT NULL DEFAULT 0,
  is_workspace_latest    INTEGER NOT NULL DEFAULT 0,
  last_scanned_at        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sessions_tool    ON sessions(tool);
CREATE INDEX IF NOT EXISTS idx_sessions_project ON sessions(project_path);
CREATE INDEX IF NOT EXISTS idx_sessions_started ON sessions(started_at);
CREATE INDEX IF NOT EXISTS idx_sessions_ended   ON sessions(ended_at);

CREATE TABLE IF NOT EXISTS prompts (
  session_id TEXT NOT NULL,
  seq        INTEGER NOT NULL,
  ts         TEXT,
  text       TEXT,
  PRIMARY KEY (session_id, seq)
);

CREATE VIRTUAL TABLE IF NOT EXISTS prompts_fts USING fts5(
  text, session_id UNINDEXED, tokenize='porter unicode61'
);

CREATE TABLE IF NOT EXISTS tags (
  session_id TEXT NOT NULL,
  tag        TEXT NOT NULL,
  PRIMARY KEY (session_id, tag),
  FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
"""


_initialized = False
_migrated = False


def _migrate(con: sqlite3.Connection) -> None:
    """Run schema migrations.  Safe to call on any existing DB."""
    global _migrated
    if _migrated:
        return

    current = None
    try:
        row = con.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
        if row:
            current = row[0]
    except sqlite3.OperationalError:
        # meta table doesn't exist yet — DDL hasn't run; nothing to migrate
        _migrated = True
        return

    if current is None or current < "2":
        # Create FTS5 and tags tables if they don't already exist
        con.executescript("""
            CREATE VIRTUAL TABLE IF NOT EXISTS prompts_fts USING fts5(
                text, session_id UNINDEXED, tokenize='porter unicode61'
            );
            CREATE TABLE IF NOT EXISTS tags (
                session_id TEXT NOT NULL,
                tag        TEXT NOT NULL,
                PRIMARY KEY (session_id, tag),
                FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
            );
        """)
        con.execute(
            "INSERT INTO meta(key, value) VALUES ('schema_version', '2') "
            "ON CONFLICT(key) DO UPDATE SET value='2'"
        )
        con.commit()

    _migrated = True


def connect() -> sqlite3.Connection:
    global _initialized
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(config.INDEX_DB)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA foreign_keys = ON")
    if not _initialized:
        con.executescript(DDL)
        con.execute(
            "INSERT OR IGNORE INTO meta(key, value) VALUES ('schema_version', ?)",
            (SCHEMA_VERSION,),
        )
        con.commit()
        _initialized = True
    _migrate(con)
    return con


def get_meta(con: sqlite3.Connection, key: str) -> str | None:
    row = con.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else None


def set_meta(con: sqlite3.Connection, key: str, value: str) -> None:
    con.execute(
        "INSERT INTO meta(key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )
