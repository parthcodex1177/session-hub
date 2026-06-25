#!/usr/bin/env bash
# Quick-start: create venv if needed, then run Session Hub.
#   ./run.sh            → server + browser tab (http://127.0.0.1:8788/)
#   ./run.sh --app      → native window (GTK/WebKit on Linux, WKWebView on macOS)
#   ./run.sh --scan-only→ index only, print summary, exit
#   ./run.sh --port 9000→ custom port
set -e
cd "$(dirname "$0")"

# For the native window, make sure GTK3 + WebKit2GTK are installed (Linux).
if [ "${1:-}" = "--app" ]; then
    # shellcheck source=scripts/ensure-gui-deps.sh
    . "$(dirname "$0")/scripts/ensure-gui-deps.sh"
    ensure_gui_deps || echo "warning: native window may not open; try browser mode: ./run.sh" >&2
fi

if [ ! -d .venv ]; then
    # Linux: --system-site-packages so pywebview can reach GTK/WebKit2 system libs.
    # macOS/other: plain venv (pywebview brings its own WKWebView bridge via PyObjC).
    if [ "$(uname)" = "Linux" ]; then
        python3 -m venv --system-site-packages .venv
    else
        python3 -m venv .venv
    fi
    # editable install needs setuptools>=64 (PEP 660); distro venvs ship older.
    # On Linux --system-site-packages exposes the distro's ancient
    # importlib_metadata + packaging (Ubuntu 20.04 = 1.x / 20.x), which break
    # modern setuptools on Python 3.8; upgrading them in the venv shadows the
    # system copies.
    .venv/bin/python -m pip install -q --upgrade pip setuptools wheel importlib-metadata packaging
    # [native] pulls pywebview so `--app` works; harmless for browser mode.
    .venv/bin/pip install -q -e ".[native]"
fi

if [ "${1:-}" = "--app" ]; then
    shift
    exec .venv/bin/session-hub-app "$@"
fi
exec .venv/bin/session-hub "$@"
