#!/usr/bin/env bash
# Quick-start: create venv if needed, then run Session Hub.
#   ./run.sh            → server + browser tab (http://127.0.0.1:8788/)
#   ./run.sh --app      → native window (GTK/WebKit on Linux, WKWebView on macOS)
#   ./run.sh --scan-only→ index only, print summary, exit
#   ./run.sh --port 9000→ custom port
set -e
cd "$(dirname "$0")"

if [ ! -d .venv ]; then
    # Linux: --system-site-packages so pywebview can reach GTK/WebKit2 system libs.
    # macOS/other: plain venv (pywebview brings its own WKWebView bridge via PyObjC).
    if [ "$(uname)" = "Linux" ]; then
        python3 -m venv --system-site-packages .venv
    else
        python3 -m venv .venv
    fi
    .venv/bin/pip install -q -e .
fi

if [ "${1:-}" = "--app" ]; then
    shift
    exec .venv/bin/session-hub-app "$@"
fi
exec .venv/bin/session-hub "$@"
