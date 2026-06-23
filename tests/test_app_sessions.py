"""HTTP-boundary tests for sessionhub.app /api/sessions (priority: high/low).

We seed a tmp sqlite DB (real schema via sessionhub.db.DDL) and point the
app at it by monkeypatching sessionhub.app._connect. active_sessions() is
also monkeypatched so the tests never read real ~/.claude/sessions data.
"""
import sqlite3

import pytest
from fastapi.testclient import TestClient

from sessionhub import app as app_module
from sessionhub import db


# Minimal NOT NULL fields required by the sessions schema.
def _insert_session(
    con,
    *,
    sid,
    started_at,
    file_path,
    tool="claude",
    user_prompt_count=1,
    ended_at=None,
):
    con.execute(
        """
        INSERT INTO sessions (
            id, tool, title, project_path, project_name,
            started_at, ended_at, user_prompt_count,
            file_path, file_mtime, file_size, last_scanned_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            sid,
            tool,
            f"title-{sid}",
            "/home/dev/proj",
            "proj",
            started_at,
            ended_at or started_at,
            user_prompt_count,
            file_path,
            1.0,
            100,
            "2026-06-11T00:00:00Z",
        ),
    )


@pytest.fixture
def seeded_db_path(tmp_path):
    """Create a tmp DB file with the real schema and three seeded sessions."""
    db_path = tmp_path / "index.db"
    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    con.executescript(db.DDL)
    _insert_session(
        con, sid="s1", started_at="2026-06-11T00:00:00Z", file_path="/f/1.jsonl"
    )
    _insert_session(
        con, sid="s2", started_at="2026-06-11T23:59:59Z", file_path="/f/2.jsonl"
    )
    _insert_session(
        con, sid="s3", started_at="2026-06-12T00:00:00Z", file_path="/f/3.jsonl"
    )
    con.commit()
    con.close()
    return db_path


@pytest.fixture
def client(seeded_db_path, monkeypatch):
    """TestClient whose every request opens a fresh connection to the tmp DB."""

    def _connect():
        con = sqlite3.connect(str(seeded_db_path))
        con.row_factory = sqlite3.Row
        return con

    monkeypatch.setattr(app_module, "_connect", _connect)
    # Never read real live-session data from ~/.claude/sessions.
    monkeypatch.setattr(app_module, "active_sessions", lambda: {})
    return TestClient(app_module.app)


def test_list_sessions_date_to_includes_whole_day_excludes_next_day(client):
    resp = client.get("/api/sessions", params={"date_to": "2026-06-11"})
    assert resp.status_code == 200
    body = resp.json()

    returned_ids = {item["id"] for item in body["items"]}
    assert returned_ids == {"s1", "s2"}
    assert body["total"] == 2


def test_list_sessions_sort_injection_payload_is_rejected_to_default_order(client):
    # A SQL-injection-style sort value must fall back to the default column,
    # return 200, and leave the sessions table intact.
    resp = client.get(
        "/api/sessions", params={"sort": "id; DROP TABLE sessions"}
    )
    assert resp.status_code == 200

    # All three seeded rows still present — table was not dropped.
    body = resp.json()
    assert body["total"] == 3

    # Verify default ordering is by ended_at DESC (s3 newest, s1 oldest).
    ids_in_order = [item["id"] for item in body["items"]]
    assert ids_in_order == ["s3", "s2", "s1"]
