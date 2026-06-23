"""Tests for scripts/ensure-gui-deps.sh (priority: high).

These shell functions decide whether/how to install the native-window system
libraries. The risky bits are: never hang without a tty, pick the webkit
package the distro actually has, and no-op off Linux. We exercise them by
sourcing the script in bash with a stubbed PATH (fake python3 / apt-cache /
uname), so nothing real is installed.
"""
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "ensure-gui-deps.sh"

pytestmark = pytest.mark.skipif(
    shutil.which("bash") is None, reason="bash required"
)


def _run(snippet: str, stubs: dict[str, str], tmp_path, stdin_devnull=True):
    """Run a bash snippet that sources the script, with `stubs` as PATH executables."""
    bindir = tmp_path / "bin"
    bindir.mkdir(exist_ok=True)
    for name, body in stubs.items():
        p = bindir / name
        p.write_text("#!/bin/sh\n" + body + "\n")
        p.chmod(0o755)
    cmd = f'. "{SCRIPT}"\n{snippet}'
    redirect = subprocess.DEVNULL if stdin_devnull else None
    return subprocess.run(
        ["bash", "-c", cmd],
        env={"PATH": f"{bindir}:/usr/bin:/bin"},
        capture_output=True,
        text=True,
        stdin=redirect,
        timeout=15,
    )


def test_no_op_on_non_linux(tmp_path):
    # uname != Linux  → ensure_gui_deps returns 0 immediately, never touches apt.
    r = _run(
        "ensure_gui_deps; echo rc=$?",
        {"uname": "echo Darwin", "apt-get": "echo SHOULD_NOT_RUN; exit 1"},
        tmp_path,
    )
    assert "rc=0" in r.stdout
    assert "SHOULD_NOT_RUN" not in r.stdout


def test_no_tty_missing_deps_returns_fast_without_apt(tmp_path):
    # Linux + deps missing + no tty (stdin /dev/null) → must NOT hang and must
    # NOT invoke apt-get; returns non-zero so the caller can notify instead.
    r = _run(
        "ensure_gui_deps; echo rc=$?",
        {
            "uname": "echo Linux",
            "python3": "exit 1",  # gui_deps_ok fails → deps missing
            "apt-get": "echo APT_RAN; exit 0",
        },
        tmp_path,
    )
    assert "rc=1" in r.stdout
    assert "APT_RAN" not in r.stdout  # never reached apt


def test_webkit_pkg_prefers_41_then_40(tmp_path):
    # apt-cache "knows" both → pick 4.1; only 4.0 → pick 4.0; neither → rc 1.
    both = _run(
        '_webkit_pkg; echo rc=$?',
        {"apt-cache": 'case "$2" in *4.1) exit 0;; *4.0) exit 0;; esac; exit 1'},
        tmp_path,
    )
    assert both.stdout.splitlines()[0] == "gir1.2-webkit2-4.1"

    only40 = _run(
        '_webkit_pkg; echo rc=$?',
        {"apt-cache": 'case "$2" in *4.0) exit 0;; esac; exit 1'},
        tmp_path,
    )
    assert only40.stdout.splitlines()[0] == "gir1.2-webkit2-4.0"

    neither = _run(
        '_webkit_pkg && echo FOUND || echo rc=$?',
        {"apt-cache": "exit 1"},
        tmp_path,
    )
    assert "rc=1" in neither.stdout
    assert "FOUND" not in neither.stdout


def test_guarded_call_does_not_kill_set_e_parent(tmp_path):
    # A guarded `ensure_gui_deps || true` must not abort a `set -e` parent.
    r = _run(
        'set -e; ensure_gui_deps || true; echo SURVIVED',
        {"uname": "echo Linux", "python3": "exit 1"},
        tmp_path,
    )
    assert "SURVIVED" in r.stdout
