"""Tests for sessionhub.parse_claude (priority: medium).

is_real_prompt filtering and parse_claude_file malformed-line tolerance.
"""
import json

import pytest

from sessionhub.parse_claude import is_real_prompt, parse_claude_file


@pytest.mark.parametrize(
    "text, expected",
    [
        pytest.param("/clear", False, id="bare_slash_command"),
        pytest.param("/model:opus", False, id="slash_command_with_colon"),
        pytest.param("<system-reminder>x", False, id="angle_bracket_tag"),
        pytest.param("Caveat: ...", False, id="caveat_prefix"),
        pytest.param("", False, id="empty_string"),
        pytest.param("fix the bug in scanner", True, id="real_user_prompt"),
    ],
)
def test_is_real_prompt_classifies_text(text, expected):
    assert is_real_prompt(text) is expected


def test_parse_claude_file_counts_malformed_lines_and_keeps_valid_prompt(tmp_path):
    valid_entry = {
        "type": "user",
        "timestamp": "2026-06-11T10:00:00Z",
        "cwd": "/home/dev/myproject",
        "message": {"content": "fix the scanner bug"},
    }
    jsonl = tmp_path / "session.jsonl"
    jsonl.write_text(
        "\n".join(
            [
                json.dumps(valid_entry),
                "{ this is not valid json",   # malformed: JSON decode error
                json.dumps(["a", "list", "not", "a", "dict"]),  # valid JSON, wrong shape
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    rec = parse_claude_file(jsonl)

    # Both the broken line and the JSON-array line count as malformed.
    assert rec.malformed_lines == 2
    # The single valid user prompt was captured.
    assert rec.user_prompt_count == 1
    assert rec.prompts[0][1] == "fix the scanner bug"
    # project_path comes from the valid entry's cwd.
    assert rec.project_path == "/home/dev/myproject"
