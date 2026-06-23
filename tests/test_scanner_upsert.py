"""Tests for sessionhub.scanner._upsert cross-dir uuid collision (priority: high).

Same session uuid appearing under two project directories: the scanner keeps
the larger file and never duplicates the row. We drive _upsert directly with a
tmp DB connection so no real index is touched.
"""
from sessionhub.parse_claude import SessionRecord
from sessionhub.scanner import ScanSummary, _upsert

UUID = "12345678-1234-1234-1234-123456789abc"


def _record(*, file_path, file_size):
    return SessionRecord(
        id=UUID,
        tool="claude",
        file_path=file_path,
        file_mtime=1.0,
        file_size=file_size,
        title="t",
        project_path="/home/dev/proj",
    )


def _stored_row(con):
    return con.execute(
        "SELECT file_path, file_size FROM sessions WHERE id = ?", (UUID,)
    ).fetchone()


def test_upsert_new_uuid_inserts_and_counts_as_added(tmp_db):
    summary = ScanSummary()
    _upsert(tmp_db, _record(file_path="/p1/s.jsonl", file_size=100), summary)

    row = _stored_row(tmp_db)
    assert row["file_path"] == "/p1/s.jsonl"
    assert row["file_size"] == 100
    assert summary.sessions_added == 1
    assert summary.sessions_updated == 0


def test_upsert_same_uuid_smaller_file_is_ignored_and_keeps_original(tmp_db):
    summary = ScanSummary()
    _upsert(tmp_db, _record(file_path="/p1/s.jsonl", file_size=100), summary)
    _upsert(tmp_db, _record(file_path="/p2/s.jsonl", file_size=50), summary)

    # Early return: row unchanged, counts unchanged from the first insert.
    row = _stored_row(tmp_db)
    assert row["file_path"] == "/p1/s.jsonl"
    assert row["file_size"] == 100
    assert summary.sessions_added == 1
    assert summary.sessions_updated == 0


def test_upsert_same_uuid_larger_file_relocates_and_counts_as_updated(tmp_db):
    summary = ScanSummary()
    _upsert(tmp_db, _record(file_path="/p1/s.jsonl", file_size=100), summary)
    _upsert(tmp_db, _record(file_path="/p2/s.jsonl", file_size=200), summary)

    # Relocated to the larger file; counted as an update, not a duplicate add.
    row = _stored_row(tmp_db)
    assert row["file_path"] == "/p2/s.jsonl"
    assert row["file_size"] == 200
    assert summary.sessions_added == 1
    assert summary.sessions_updated == 1

    # Still exactly one row for this uuid — no duplicate.
    count = tmp_db.execute(
        "SELECT count(*) AS c FROM sessions WHERE id = ?", (UUID,)
    ).fetchone()["c"]
    assert count == 1
