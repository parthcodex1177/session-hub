#!/usr/bin/env bash
# Install — or update — Session Hub and add it to the application / start menu.
#
#   curl -fsSL https://raw.githubusercontent.com/parthcodex1177/session-hub/main/install-pipx.sh | bash
#
# Run the SAME command again any time to update to the latest version. It is
# fully idempotent: it installs pipx if missing, (re)installs Session Hub from
# GitHub, and registers the menu icon. Works on any system with Python 3.8+.
set -euo pipefail

REPO_URL="git+https://github.com/parthcodex1177/session-hub.git"

have() { command -v "$1" >/dev/null 2>&1; }

# 1. Python 3.8+ is required (the app itself; end users need nothing else).
if ! have python3; then
    echo "Python 3 is required. Install it first, e.g.:" >&2
    echo "  sudo apt install -y python3 python3-venv python3-pip" >&2
    exit 1
fi

# 2. Ensure pipx is available. On PEP 668 "externally-managed" Pythons
#    (Debian 12+/Ubuntu 23.04+/Fedora) `pip install --user` is blocked, so
#    fall back to telling the user to install pipx via their OS package manager.
if ! have pipx && ! python3 -m pipx --version >/dev/null 2>&1; then
    echo "Installing pipx..."
    if ! python3 -m pip install --user -q pipx 2>/dev/null; then
        echo "Could not install pipx via pip (your Python may be externally managed / PEP 668)." >&2
        echo "Install pipx with your OS package manager, then re-run this script:" >&2
        echo "  Debian/Ubuntu: sudo apt install -y pipx" >&2
        echo "  Fedora:        sudo dnf install -y pipx" >&2
        echo "  macOS (brew):  brew install pipx" >&2
        exit 1
    fi
    python3 -m pipx ensurepath >/dev/null 2>&1 || true
fi
PIPX="pipx"
have pipx || PIPX="python3 -m pipx"

# 3. Install or update. `--force` both installs fresh and reinstalls from the
#    latest commit (plain `pipx upgrade` won't, because the version is static),
#    so this single idempotent command covers first-install and update alike.
echo "Installing / updating Session Hub..."
$PIPX install --force "$REPO_URL"

# 4. Register the application-menu entry (Linux). Call by absolute path because
#    ~/.local/bin may not be on PATH yet in this shell.
BIN="$HOME/.local/bin/session-hub"
if [ -x "$BIN" ]; then
    "$BIN" --install-desktop || true
fi

echo
echo "Done. Launch 'Session Hub' from your application menu,"
echo "or run 'session-hub' in a terminal."
echo "If the menu icon isn't visible yet: GNOME on X11 -> Alt+F2, type 'r', Enter"
echo "(otherwise log out and back in). Re-run this command any time to update."
