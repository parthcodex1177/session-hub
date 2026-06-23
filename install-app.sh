#!/usr/bin/env bash
# Install Session Hub as a native Ubuntu desktop application:
#   - a .desktop entry in the GNOME app grid / dock (click to launch)
#   - a `session-hub` command on PATH (type it anywhere)
# Re-run any time to refresh. Uninstall with ./install-app.sh --uninstall
set -euo pipefail

DIR="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
LAUNCHER="$DIR/session-hub-launch.sh"
APPS="$HOME/.local/share/applications"
DESKTOP="$APPS/session-hub.desktop"
BIN="$HOME/.local/bin/session-hub"
ICON_DIR="$HOME/.local/share/icons/hicolor/scalable/apps"
ICON_DEST="$ICON_DIR/session-hub.svg"

if [ "${1:-}" = "--uninstall" ]; then
    rm -f "$DESKTOP" "$BIN" "$ICON_DEST"
    command -v update-desktop-database >/dev/null && update-desktop-database "$APPS" || true
    echo "Session Hub app removed."
    exit 0
fi

chmod +x "$LAUNCHER"
mkdir -p "$APPS" "$HOME/.local/bin" "$ICON_DIR"

# Install the icon into the theme tree so the entry isn't coupled to the
# repo path and can be referenced by name.
if [ -f "$DIR/assets/session-hub.svg" ]; then
    cp "$DIR/assets/session-hub.svg" "$ICON_DEST"
else
    echo "warning: assets/session-hub.svg missing; entry will use a fallback icon" >&2
fi

cat > "$DESKTOP" <<EOF
[Desktop Entry]
Type=Application
Version=1.0
Name=Session Hub
GenericName=AI Session History
Comment=Browse, search and resume Claude Code & Antigravity sessions
Exec=$LAUNCHER
Icon=session-hub
Terminal=false
Categories=Development;
Keywords=claude;antigravity;agy;session;history;resume;
StartupNotify=true
StartupWMClass=session-hub
EOF
chmod +x "$DESKTOP"

ln -sf "$LAUNCHER" "$BIN"

command -v update-desktop-database >/dev/null && update-desktop-database "$APPS" || true
command -v gtk-update-icon-cache >/dev/null && gtk-update-icon-cache -q -f -t \
    "$HOME/.local/share/icons/hicolor" 2>/dev/null || true

echo "Installed:"
echo "  App menu entry : $DESKTOP"
echo "  Terminal command: session-hub  ->  $LAUNCHER"
echo
echo "Search 'Session Hub' in Activities, or run 'session-hub' in any terminal."
