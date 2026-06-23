"""Tests for sessionhub.resume.build_command (priority: high).

build_command takes a sqlite3.Row or any mapping supporting row["key"];
a plain dict works. We only exercise build_command here — never
launch_terminal, which would spawn a real terminal process.
"""
import shlex

import pytest

from sessionhub.resume import ResumeError, build_command

VALID_UUID = "12345678-1234-1234-1234-123456789abc"


def _claude_row(**overrides):
    row = {
        "id": VALID_UUID,
        "tool": "claude",
        "project_path": "/home/dev/project",
        "is_workspace_latest": 0,
    }
    row.update(overrides)
    return row


def _antigravity_row(**overrides):
    row = {
        "id": VALID_UUID,
        "tool": "antigravity",
        "project_path": "/home/dev/workspace",
        "is_workspace_latest": 0,
    }
    row.update(overrides)
    return row


def test_build_command_valid_claude_row_returns_resume_command():
    cmd = build_command(_claude_row())
    assert cmd == f"cd {shlex.quote('/home/dev/project')} && claude --resume {VALID_UUID}"


def test_build_command_non_uuid_id_raises_resume_error_400():
    with pytest.raises(ResumeError) as exc_info:
        build_command(_claude_row(id="not-a-uuid"))
    assert exc_info.value.status == 400


def test_build_command_antigravity_returns_agy_conversation_command():
    # agy supports resume-by-id via --conversation, regardless of
    # is_workspace_latest
    for latest in (0, 1):
        cmd = build_command(_antigravity_row(is_workspace_latest=latest))
        assert cmd == (
            f"cd {shlex.quote('/home/dev/workspace')} "
            f"&& agy --conversation {VALID_UUID}"
        )


def test_build_command_project_path_with_shell_metacharacters_is_quoted():
    dangerous = '/tmp/a b/"$(touch x)"/c'
    cmd = build_command(_claude_row(project_path=dangerous))

    # The path must appear in its shlex-quoted form.
    quoted = shlex.quote(dangerous)
    assert quoted in cmd

    # No unescaped command-substitution outside of single quotes: every
    # occurrence of "$(" must live inside a single-quoted span. shlex.quote
    # wraps the whole value in single quotes, so the only "$(" present is the
    # safe, quoted one. Assert that stripping the quoted span removes it.
    assert "$(" in cmd  # sanity: the payload is actually present
    assert "$(" not in cmd.replace(quoted, "")


def test_build_command_project_path_none_raises_resume_error_409():
    with pytest.raises(ResumeError) as exc_info:
        build_command(_claude_row(project_path=None))
    assert exc_info.value.status == 409
