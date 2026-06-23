#!/usr/bin/env bash
# Launch Session Hub as a native desktop window (pywebview + WebKit).
# The app runs its own server on a private localhost port inside the process,
# so there is no browser and no fixed port to manage. Single-instance: a
# second launch while one is open exits quietly (the open window stays).
#
#   session-hub-launch.sh            normal launch (single-instance)
#   session-hub-launch.sh --restart  kill any running instance first, then
#                                     relaunch — use this after upgrading.
set -euo pipefail

DIR="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
STATE="${XDG_STATE_HOME:-$HOME/.local/state}/session-hub"
LOGFILE="$STATE/app.log"
LOCK="$STATE/app.lock"
READY="$STATE/ready.$$"
mkdir -p "$STATE"
rm -f "$READY"

# --restart: stop a running instance so the new code takes effect. Matches the
# GUI binary path precisely so it never kills this launcher or unrelated procs.
if [ "${1:-}" = "--restart" ]; then
    for p in $(pgrep -f "$DIR/.venv/bin/session-hub-app" 2>/dev/null); do
        kill "$p" 2>/dev/null || true
    done
    # wait (up to ~5s) for the old instance to exit and release the lock
    for _ in $(seq 1 25); do
        pgrep -f "$DIR/.venv/bin/session-hub-app" >/dev/null 2>&1 || break
        sleep 0.2
    done
fi

# Bootstrap the virtualenv on first run. --system-site-packages lets it see the
# system PyGObject/WebKit2 that pywebview's GTK backend needs.
if [ ! -x "$DIR/.venv/bin/session-hub-app" ]; then
    [ -d "$DIR/.venv" ] || python3 -m venv --system-site-packages "$DIR/.venv"
    "$DIR/.venv/bin/pip" install -q -e "$DIR"
fi

# Single-instance guard: if another launch holds the lock, do nothing. The
# lock is held (fd 9 stays open) for this launcher's whole life, i.e. for the
# window's lifetime.
exec 9>"$LOCK"
if ! flock -n 9; then
    exit 0
fi

# Start the GUI. Success is "the window came up" (the ready file appears), not
# the process exit code — see desktop.py for why the exit code is unreliable.
SESSION_HUB_READY_FILE="$READY" "$DIR/.venv/bin/session-hub-app" \
    >>"$LOGFILE" 2>&1 &
gui=$!

started=0
for _ in $(seq 1 75); do          # wait up to ~15s for the window
    # Success = this child signaled ready AND is still alive (never trust a
    # leftover ready-file on its own).
    if [ -f "$READY" ] && kill -0 "$gui" 2>/dev/null; then
        started=1
        break
    fi
    kill -0 "$gui" 2>/dev/null || break   # process died before showing a window
    sleep 0.2
done
rm -f "$READY"

if [ "$started" = 1 ]; then
    wait "$gui" 2>/dev/null || true       # hold the lock until the window closes
    exit 0
fi

command -v notify-send >/dev/null && \
    notify-send "Session Hub" "Failed to start — see $LOGFILE" || true
echo "Session Hub failed to start; see $LOGFILE" >&2
exit 1
