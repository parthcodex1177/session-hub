"""Standalone entry point for the bundled single-file binary.

Starts the embedded server and opens the dashboard in the user's default
browser. Has NO native-GUI dependency (no GTK/WebKit), so PyInstaller can
freeze it into one executable that runs on any machine without Python or
system libraries installed.
"""
from __future__ import annotations

import socket
import threading
import time
import webbrowser

from . import config, db
from .app import app
from .scanner import scan


def _pick_port() -> int:
    """Prefer the default port; fall back to an OS-assigned free one."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind((config.HOST, config.PORT))
            return config.PORT
        except OSError:
            s.bind((config.HOST, 0))
            return s.getsockname()[1]


def _open_when_ready(host: str, port: int, url: str) -> None:
    """Open the browser only once the server actually accepts connections, so
    the user never lands on a connection-refused page on a slow first start."""
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex((host, port)) == 0:
                webbrowser.open(url)
                return
        time.sleep(0.1)
    webbrowser.open(url)  # gave up waiting; open anyway, user can refresh


def main():
    # Build / refresh the index before the page loads.
    con = db.connect()
    try:
        scan(con)
    finally:
        con.close()

    import uvicorn

    port = _pick_port()
    url = f"http://{config.HOST}:{port}/"

    # Daemon thread: opens the browser when the port is live; never blocks exit.
    threading.Thread(
        target=_open_when_ready, args=(config.HOST, port, url), daemon=True
    ).start()

    print(f"\n  Session Hub is running at {url}")
    print("  Your browser should open automatically. Press Ctrl+C to stop.\n")
    uvicorn.run(app, host=config.HOST, port=port, log_level="warning")


if __name__ == "__main__":
    main()
