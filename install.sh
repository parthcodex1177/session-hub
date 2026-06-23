#!/usr/bin/env bash
# Session Hub installer — downloads the prebuilt binary (no Python needed) and
# wires up the `session-hub` command plus an app-menu entry.
#
# One-liner:
#   curl -fsSL https://raw.githubusercontent.com/parthcodex1177/session-hub/main/install.sh | bash
#
# Re-run any time to update to the latest release.
set -euo pipefail

REPO="parthcodex1177/session-hub"
BIN_DIR="$HOME/.local/bin"
BIN="$BIN_DIR/session-hub"

os="$(uname -s)"
arch="$(uname -m)"
case "$os/$arch" in
    Linux/x86_64)        asset="session-hub-linux-x86_64" ;;
    Darwin/arm64)        asset="session-hub-macos-arm64" ;;
    Darwin/x86_64)
        echo "No prebuilt Intel-mac binary yet. Run from source instead:" >&2
        echo "  git clone https://github.com/$REPO && cd session-hub && ./run.sh" >&2
        exit 1 ;;
    *)
        echo "No prebuilt binary for $os/$arch. Run from source:" >&2
        echo "  git clone https://github.com/$REPO && cd session-hub && ./run.sh" >&2
        exit 1 ;;
esac

url="https://github.com/$REPO/releases/latest/download/$asset"
mkdir -p "$BIN_DIR"

echo "Downloading $asset from the latest release…"
if command -v curl >/dev/null 2>&1; then
    curl -fSL "$url" -o "$BIN"
elif command -v wget >/dev/null 2>&1; then
    wget -O "$BIN" "$url"
else
    echo "Need curl or wget to download." >&2
    exit 1
fi
chmod +x "$BIN"

# App-menu entry + icon (Linux desktops only).
if [ "$os" = "Linux" ]; then
    APPS="$HOME/.local/share/applications"
    ICON_DIR="$HOME/.local/share/icons/hicolor/scalable/apps"
    mkdir -p "$APPS" "$ICON_DIR"
    curl -fsSL "https://raw.githubusercontent.com/$REPO/main/assets/session-hub.svg" \
        -o "$ICON_DIR/session-hub.svg" 2>/dev/null || true
    cat > "$APPS/session-hub.desktop" <<EOF
[Desktop Entry]
Type=Application
Version=1.0
Name=Session Hub
GenericName=AI Session History
Comment=Browse, search and resume Claude Code & Antigravity sessions
Exec=$BIN
Icon=session-hub
Terminal=false
Categories=Development;
Keywords=claude;antigravity;agy;session;history;resume;
EOF
    command -v update-desktop-database >/dev/null 2>&1 && \
        update-desktop-database "$APPS" 2>/dev/null || true
fi

echo
echo "Installed: $BIN"
echo "Run it:    session-hub      (or click 'Session Hub' in your app menu)"
case ":$PATH:" in
    *":$BIN_DIR:"*) ;;
    *) echo
       echo "NOTE: $BIN_DIR is not on your PATH. Add this to ~/.bashrc:"
       echo "      export PATH=\"\$HOME/.local/bin:\$PATH\"" ;;
esac
