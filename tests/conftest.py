"""Shared fixtures for the session-hub test suite.

All fixtures here guarantee tests NEVER touch the real index DB
(~/.local/share/session-hub/index.db) or real ~/.claude data. DB-backed
tests use a tmp sqlite file and apply sessionhub.db.DDL via executescript
directly, rather than db.connect() which targets the real path.
"""
import sqlite3

import pytest

from sessionhub import db


def _new_db(path) -> sqlite3.Connection:
    """Create a fresh sqlite connection at ``path`` with the real schema applied.

    Applies sessionhub.db.DDL directly via executescript so we exercise the
    production schema without going through db.connect() (which would target
    the real ~/.local/share path).
    """
    con = sqlite3.connect(str(path))
    con.row_factory = sqlite3.Row
    con.executescript(db.DDL)
    con.execute(
        "INSERT OR IGNORE INTO meta(key, value) VALUES ('schema_version', ?)",
        (db.SCHEMA_VERSION,),
    )
    con.commit()
    return con


@pytest.fixture
def tmp_db(tmp_path):
    """A function-scoped sqlite connection on a tmp file with the real schema."""
    con = _new_db(tmp_path / "index.db")
    try:
        yield con
    finally:
        con.close()


@pytest.fixture
def make_db(tmp_path):
    """Factory that builds independent tmp DB connections at distinct paths."""
    created = []

    def _factory(name="index.db"):
        con = _new_db(tmp_path / name)
        created.append(con)
        return con

    yield _factory
    for con in created:
        con.close()
