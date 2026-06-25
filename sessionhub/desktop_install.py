"""Create / remove a desktop menu entry for Session Hub.

pipx (and pip) only put console scripts on PATH; they never register an
application menu entry. This module writes a freedesktop ``.desktop`` file and
icon into the user's ``~/.local/share`` so "Session Hub" shows up in the app
grid / start menu on Linux — no manual steps, no copy-paste.

The menu entry launches ``session-hub-standalone`` (browser mode), which is
single-instance: clicking the icon again reuses the running server instead of
spawning a duplicate. Native-window mode is intentionally NOT used here because
pipx venvs are isolated and cannot import the system GTK/PyGObject bindings.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

APP_ID = "session-hub"


def _data_home() -> Path:
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))


def _desktop_path() -> Path:
    return _data_home() / "applications" / f"{APP_ID}.desktop"


def _icon_path() -> Path:
    return _data_home() / "icons" / "hicolor" / "scalable" / "apps" / f"{APP_ID}.svg"


def _bundled_icon() -> Path:
    """Locate the packaged icon, whether running from source or a frozen build."""
    meipass = getattr(sys, "_MEIPASS", None)
    base = Path(meipass) / "sessionhub" if meipass else Path(__file__).parent
    return base / f"{APP_ID}.svg"


def _launcher_command() -> str:
    """Absolute path to the browser launcher (session-hub-standalone).

    Prefer the sibling of the running executable so it resolves correctly inside
    a pipx venv — but only when argv[0] actually carries a path, otherwise a
    bare name like "session-hub" would resolve against the CWD and bake a wrong
    path into the .desktop. Fall back to PATH lookup, then a bare command name.
    """
    arg0 = sys.argv[0]
    has_path = os.sep in arg0 or bool(os.altsep and os.altsep in arg0)
    if has_path:
        sibling = Path(arg0).resolve().parent / "session-hub-standalone"
        if sibling.exists():
            return str(sibling)
    return shutil.which("session-hub-standalone") or "session-hub-standalone"


def _exec_quote(path: str) -> str:
    """Quote a path for a freedesktop Exec= value (double-quote + escape the
    reserved characters), so paths with spaces or shell metacharacters are
    neither broken nor injectable."""
    escaped = (
        path.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("`", "\\`")
        .replace("$", "\\$")
    )
    return f'"{escaped}"'


def _atomic_write(dest: Path, text: str) -> None:
    """Write text to dest atomically (temp file + rename in the same dir) so an
    interruption never leaves a half-written, corrupt .desktop entry."""
    fd, tmp = tempfile.mkstemp(dir=str(dest.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(text)
        os.replace(tmp, dest)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _refresh_menu(applications_dir: Path) -> None:
    if shutil.which("update-desktop-database"):
        subprocess.run(
            ["update-desktop-database", str(applications_dir)],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


def install_desktop() -> int:
    """Write the menu entry + icon. Returns a process exit code."""
    if sys.platform != "linux":
        print(
            "--install-desktop is Linux-only. On macOS/Windows just run "
            "'session-hub' or 'session-hub-standalone'."
        )
        return 0

    icon_src = _bundled_icon()
    icon_dst = _icon_path()
    desktop = _desktop_path()
    exec_cmd = _launcher_command()

    icon_line = "Icon=session-hub"
    try:
        if icon_src.exists():
            icon_dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(icon_src, icon_dst)
        else:
            # No bundled icon (shouldn't happen) — fall back to a stock icon.
            icon_line = "Icon=utilities-terminal"

        entry = f"""[Desktop Entry]
Type=Application
Version=1.0
Name=Session Hub
GenericName=AI Session History
Comment=Browse, search and resume Claude Code & Antigravity sessions
Exec={_exec_quote(exec_cmd)}
{icon_line}
Terminal=false
Categories=Development;
Keywords=claude;antigravity;session;history;resume;
StartupNotify=true
"""
        desktop.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write(desktop, entry)
    except OSError as exc:
        print(f"Could not write the menu entry: {exc}", file=sys.stderr)
        print(
            "Check that your home directory is writable and not owned by root "
            "(don't run this with sudo).",
            file=sys.stderr,
        )
        return 1

    _refresh_menu(desktop.parent)

    print(f"Installed menu entry: {desktop}")
    print(f"Launches: {exec_cmd}")
    print(
        "\nIf 'Session Hub' is not in your app menu yet, reload the shell:\n"
        "  GNOME on X11: press Alt+F2, type 'r', press Enter\n"
        "  otherwise:    log out and back in"
    )
    return 0


def uninstall_desktop() -> int:
    """Remove the menu entry + icon. Returns a process exit code."""
    removed = []
    for p in (_desktop_path(), _icon_path()):
        try:
            p.unlink()
            removed.append(str(p))
        except FileNotFoundError:
            pass
        except OSError as exc:
            print(f"Could not remove {p}: {exc}", file=sys.stderr)
    _refresh_menu(_desktop_path().parent)
    if removed:
        print("Removed:\n  " + "\n  ".join(removed))
    else:
        print("Nothing to remove (no menu entry found).")
    return 0
