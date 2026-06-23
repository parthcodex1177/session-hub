"""Native desktop window for Session Hub.

Runs the existing FastAPI app on a private localhost port inside a daemon
thread, then renders the dashboard in a native WebKit window via pywebview —
no browser, no address bar, its own taskbar entry. Closing the window stops
the process (the server thread is a daemon).

This reuses 100% of the web UI; only the shell changes.
"""
import os
import socket
import threading
import time
from pathlib import Path

from . import config, db
from .app import app
from .scanner import scan


def _free_port() -> int:
    """Ask the OS for an unused localhost port (avoids clashing with a
    browser-mode server already on config.PORT)."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((config.HOST, 0))
        return s.getsockname()[1]


def main():
    # Populate the index before the window appears (warm scans are ~80ms).
    con = db.connect()
    try:
        scan(con)
    finally:
        con.close()

    # Pin the X11 WM_CLASS so GNOME maps the window to the .desktop entry
    # (StartupWMClass=session-hub) instead of showing a generic dock icon.
    try:
        from gi.repository import GLib

        GLib.set_prgname("session-hub")
        GLib.set_application_name("Session Hub")
    except Exception:
        pass

    import uvicorn
    import webview

    port = _free_port()
    server = uvicorn.Server(
        uvicorn.Config(app, host=config.HOST, port=port, log_level="warning")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    # Wait until uvicorn reports it is serving so the first paint isn't blank.
    deadline = time.monotonic() + 20
    while not server.started:
        if not thread.is_alive():
            raise RuntimeError("Session Hub server thread exited during startup")
        if time.monotonic() > deadline:
            raise RuntimeError("Session Hub server did not start within 20s")
        time.sleep(0.02)

    window = webview.create_window(
        "Session Hub",
        f"http://{config.HOST}:{port}/",
        width=1280,
        height=820,
        min_size=(900, 600),
    )

    # Tell the launcher the window is really up. The launcher decides success
    # on this file, not on our exit code: WebKit2GTK can throw a harmless
    # BadWindow during multiprocess teardown and abort with status 1, which
    # must NOT be reported to the user as "failed to start". Fire on `loaded`
    # (the page actually rendered) rather than at GUI-loop start, so a blank /
    # broken page is never reported as a successful launch.
    ready_file = os.environ.get("SESSION_HUB_READY_FILE")

    def signal_ready():
        if ready_file:
            try:
                Path(ready_file).write_text(str(port))
            except OSError:
                pass

    window.events.loaded += signal_ready

    # Blocks until the window is closed; then skip interpreter teardown to
    # dodge the WebKit2GTK shutdown X-error path (the daemon server dies too).
    webview.start()
    os._exit(0)


if __name__ == "__main__":
    main()
