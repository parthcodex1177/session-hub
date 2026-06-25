"""Regression tests for the desktop menu entry + standalone single-instance.

Covers sessionhub.desktop_install (the freedesktop .desktop / icon writer and
its Exec= quoting and launcher-command resolution) and the single-instance
guard in sessionhub.standalone.main().

Everything that would otherwise touch the real ~/.local/share goes through a
monkeypatched XDG_DATA_HOME pointing at tmp_path, so the suite stays hermetic
and never mutates the developer's app menu.
"""
from __future__ import annotations

import os
import shlex
import sys

import pytest

from sessionhub import desktop_install
from sessionhub import standalone


# --------------------------------------------------------------------------- #
# 1. _exec_quote()
# --------------------------------------------------------------------------- #
def test_exec_quote_path_with_space_roundtrips_to_single_posix_token():
    # A path containing a space must survive a POSIX word-split as exactly one
    # token equal to the original — otherwise the launcher would receive two
    # bogus argv entries.
    path = "/home/John Doe/.local/bin/session-hub-standalone"
    quoted = desktop_install._exec_quote(path)

    tokens = shlex.split(quoted)
    assert tokens == [path]


def test_exec_quote_escapes_dollar_and_backtick_inside_quotes():
    # The freedesktop spec (not shell word-splitting) governs these: the
    # reserved characters $ and ` must be backslash-escaped *inside* the double
    # quotes so a path can never be turned into a command substitution.
    path = "/opt/$HOME/`whoami`/session-hub-standalone"
    quoted = desktop_install._exec_quote(path)

    # Wrapped in double quotes.
    assert quoted.startswith('"') and quoted.endswith('"')
    # Reserved chars are backslash-escaped (do NOT use shlex as the oracle here).
    assert "\\$" in quoted
    assert "\\`" in quoted
    # And the raw, unescaped forms never appear.
    assert "$HOME" not in quoted.replace("\\$", "")
    assert quoted.count("`") == quoted.count("\\`")


# --------------------------------------------------------------------------- #
# 2. _launcher_command()
# --------------------------------------------------------------------------- #
def test_launcher_command_bare_argv0_never_returns_cwd_relative_path(monkeypatch):
    # When argv[0] is a bare name with no path separator, the resolver must NOT
    # bake a CWD-relative path into the .desktop. It must return either an
    # absolute path (from shutil.which) or the bare command name.
    # Bare name: no os.sep / os.altsep, so has_path is False and the resolver
    # must skip the sibling-of-argv0 branch entirely (which is what protected us
    # from baking a CWD-relative path).
    monkeypatch.setattr(sys, "argv", ["session-hub"])
    assert os.sep not in sys.argv[0]

    cmd = desktop_install._launcher_command()

    assert cmd == "session-hub-standalone" or os.path.isabs(cmd)
    # Never a relative path like "./session-hub-standalone" or one rooted at cwd.
    assert not cmd.startswith(".")
    assert os.getcwd() not in cmd or os.path.isabs(cmd)


# --------------------------------------------------------------------------- #
# desktop install/uninstall fixtures
# --------------------------------------------------------------------------- #
@pytest.fixture
def xdg_home(tmp_path, monkeypatch):
    """Point XDG_DATA_HOME at a tmp dir and force the Linux code path."""
    data_home = tmp_path / "xdg"
    monkeypatch.setenv("XDG_DATA_HOME", str(data_home))
    monkeypatch.setattr(sys, "platform", "linux")
    return data_home


# --------------------------------------------------------------------------- #
# 3. install_desktop() happy path + uninstall
# --------------------------------------------------------------------------- #
def test_install_desktop_writes_entry_and_icon_then_uninstall_removes_them(
    xdg_home,
):
    desktop = xdg_home / "applications" / "session-hub.desktop"
    icon = xdg_home / "icons" / "hicolor" / "scalable" / "apps" / "session-hub.svg"

    assert desktop_install.install_desktop() == 0
    assert desktop.exists()
    assert icon.exists()

    content = desktop.read_text()
    # Exec= value is double-quoted.
    exec_line = next(
        line for line in content.splitlines() if line.startswith("Exec=")
    )
    value = exec_line[len("Exec=") :]
    assert value.startswith('"') and value.endswith('"')
    # Single main category, terminated with a semicolon per the spec.
    assert "Categories=Development;" in content

    assert desktop_install.uninstall_desktop() == 0
    assert not desktop.exists()
    assert not icon.exists()


# --------------------------------------------------------------------------- #
# 4. install_desktop() idempotency
# --------------------------------------------------------------------------- #
def test_install_desktop_is_idempotent(xdg_home):
    desktop = xdg_home / "applications" / "session-hub.desktop"

    assert desktop_install.install_desktop() == 0
    first = desktop.read_text()

    assert desktop_install.install_desktop() == 0
    second = desktop.read_text()

    assert first == second


# --------------------------------------------------------------------------- #
# 5. install_desktop() failure handling (returns 1, does not raise)
# --------------------------------------------------------------------------- #
@pytest.mark.skipif(
    hasattr(os, "geteuid") and os.geteuid() == 0,
    reason="root bypasses filesystem mode bits, so the write would not fail",
)
def test_install_desktop_returns_1_when_target_unwritable(tmp_path, monkeypatch):
    # Make XDG_DATA_HOME a directory we cannot create children under, so the
    # mkdir/write fails. install_desktop must convert the OSError into a clean
    # exit code 1 and a stderr message — never let the OSError escape.
    locked = tmp_path / "locked"
    locked.mkdir()
    os.chmod(str(locked), 0o500)
    monkeypatch.setenv("XDG_DATA_HOME", str(locked))
    monkeypatch.setattr(sys, "platform", "linux")

    try:
        rc = desktop_install.install_desktop()
    finally:
        # Restore perms so tmp_path teardown can clean up.
        os.chmod(str(locked), 0o700)

    assert rc == 1


def test_install_desktop_failure_prints_to_stderr(tmp_path, monkeypatch, capsys):
    # The failure path must surface a diagnostic on stderr, not stdout.
    bad_parent = tmp_path / "afile"
    bad_parent.write_text("not a directory")
    # XDG_DATA_HOME sits *under* a regular file, so any mkdir raises NotADirectory.
    monkeypatch.setenv("XDG_DATA_HOME", str(bad_parent / "xdg"))
    monkeypatch.setattr(sys, "platform", "linux")

    rc = desktop_install.install_desktop()

    assert rc == 1
    captured = capsys.readouterr()
    assert captured.err.strip() != ""


# --------------------------------------------------------------------------- #
# 6. install_desktop() on non-Linux is a no-op
# --------------------------------------------------------------------------- #
def test_install_desktop_on_non_linux_returns_0_and_writes_nothing(
    tmp_path, monkeypatch
):
    data_home = tmp_path / "xdg"
    monkeypatch.setenv("XDG_DATA_HOME", str(data_home))
    monkeypatch.setattr(sys, "platform", "darwin")

    assert desktop_install.install_desktop() == 0
    # Nothing was created under the data home.
    assert not data_home.exists()


# --------------------------------------------------------------------------- #
# 7. standalone single-instance guard
# --------------------------------------------------------------------------- #
def test_main_reuses_running_server_and_skips_scan_and_uvicorn(monkeypatch):
    # When a server is already alive on the default port, main() must just open
    # the browser at the default URL and return — never re-scan, never start a
    # second server.
    opened = []
    monkeypatch.setattr(standalone, "_server_alive", lambda host, port: True)
    monkeypatch.setattr(standalone.webbrowser, "open", lambda url: opened.append(url))

    def _fail_scan(_con):
        raise AssertionError("scan must not run when a server is already alive")

    monkeypatch.setattr(standalone, "scan", _fail_scan)

    standalone.main()

    expected_url = f"http://{standalone.config.HOST}:{standalone.config.PORT}/"
    assert opened == [expected_url]


def test_main_proceeds_to_scan_when_no_server_alive(monkeypatch):
    # When nothing is listening, main() must build the index (call scan). We
    # raise a sentinel from scan to stop execution before uvicorn binds a port.
    class _Sentinel(Exception):
        pass

    monkeypatch.setattr(standalone, "_server_alive", lambda host, port: False)

    scan_calls = []

    def _scan(con):
        scan_calls.append(con)
        raise _Sentinel()

    monkeypatch.setattr(standalone, "scan", _scan)
    # Guard: the browser must not be opened on the default-port shortcut path.
    monkeypatch.setattr(
        standalone.webbrowser,
        "open",
        lambda url: (_ for _ in ()).throw(
            AssertionError("default-URL open must not run on the fresh-start path")
        ),
    )

    with pytest.raises(_Sentinel):
        standalone.main()

    assert len(scan_calls) == 1
