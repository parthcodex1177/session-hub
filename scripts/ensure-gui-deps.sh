#!/usr/bin/env bash
# Ensure the system libraries pywebview's native-window backend needs.
#
# On Linux that means PyGObject + GTK3 + a WebKit2GTK GI typelib. The typelib
# package name differs by release:
#   Ubuntu 20.04 / 22.04, Debian 11/12 -> gir1.2-webkit2-4.0
#   Ubuntu 23.10+ / 24.04, Debian 13   -> gir1.2-webkit2-4.1
# pywebview loads whichever is present, so we just install whatever the distro
# actually offers.
#
# Source this file, then call `ensure_gui_deps`. It is a no-op when the deps
# are already present, so it is safe to run on every install / update / launch.
# On non-Linux (macOS) it does nothing — pywebview brings its own WKWebView
# bridge via pip.

# Returns 0 if a usable GTK3 + WebKit2 GI binding is importable right now.
gui_deps_ok() {
    python3 - <<'PY' 2>/dev/null
import gi
gi.require_version("Gtk", "3.0")            # GTK3 itself — fail loud if absent
from gi.repository import Gtk  # noqa: F401
for v in ("4.1", "4.0"):                    # WebKit2 ships as 4.1 or 4.0 by distro
    try:
        gi.require_version("WebKit2", v)
        from gi.repository import WebKit2  # noqa: F401
        raise SystemExit(0)
    except SystemExit:
        raise
    except Exception:
        continue
raise SystemExit(1)
PY
}

# Pick the WebKit2 GI package this apt release actually ships.
_webkit_pkg() {
    local pkg
    for pkg in gir1.2-webkit2-4.1 gir1.2-webkit2-4.0; do
        if apt-cache show "$pkg" >/dev/null 2>&1; then
            echo "$pkg"
            return 0
        fi
    done
    return 1
}

# Ensure deps are present; install them on Debian/Ubuntu if missing.
# Returns 0 on success, 1 if it could not satisfy them.
ensure_gui_deps() {
    [ "$(uname)" = "Linux" ] || return 0          # macOS/other: nothing to do
    gui_deps_ok && return 0

    echo "Session Hub: native-window libraries (GTK3 + WebKit2GTK) are missing." >&2

    if ! command -v apt-get >/dev/null 2>&1; then
        cat >&2 <<'EOF'
Could not auto-install (apt-get not found — non-Debian system).
Install PyGObject + GTK3 + WebKit2GTK manually, e.g.:
  Fedora/RHEL : sudo dnf install python3-gobject gtk3 webkit2gtk4.1
  Arch        : sudo pacman -S python-gobject gtk3 webkit2gtk
  openSUSE    : sudo zypper install python3-gobject typelib-1_0-WebKit2-4_1
Then re-run. (Or use browser mode: run.sh — no GTK needed.)
EOF
        return 1
    fi

    local sudo_cmd=""
    if [ "$(id -u)" -ne 0 ]; then
        # No controlling terminal (e.g. launched from the GNOME icon) → we can't
        # prompt for a password and apt could hang. Bail so the caller surfaces a
        # "run in a terminal" message instead of a silent hang.
        if [ ! -t 0 ]; then
            echo "Not attached to a terminal; cannot install. Run 'session-hub' in a terminal once." >&2
            return 1
        fi
        if command -v sudo >/dev/null 2>&1; then
            sudo_cmd="sudo"
        else
            echo "Need root to install packages but 'sudo' is unavailable." >&2
            return 1
        fi
    fi

    # Fully non-interactive apt that never reads stdin, so it can't block on a
    # conffile/config prompt.
    local AE="DEBIAN_FRONTEND=noninteractive"
    # shellcheck disable=SC2086
    $sudo_cmd env $AE apt-get update -qq </dev/null || true

    local webkit_pkg
    webkit_pkg="$(_webkit_pkg || true)"
    # Last-resort guess favours 4.0 — the package the older releases this targets
    # actually ship (newer releases that have 4.1 are detected above).
    [ -n "$webkit_pkg" ] || webkit_pkg="gir1.2-webkit2-4.0"

    echo "Installing: python3-gi gir1.2-gtk-3.0 $webkit_pkg (you may be asked for your password)…" >&2
    # shellcheck disable=SC2086
    if ! $sudo_cmd env $AE apt-get install -y \
            -o Dpkg::Options::=--force-confdef -o Dpkg::Options::=--force-confold \
            python3-gi gir1.2-gtk-3.0 "$webkit_pkg" </dev/null; then
        echo "Package install failed. Try browser mode instead: ./run.sh" >&2
        return 1
    fi

    if gui_deps_ok; then
        echo "Session Hub: GUI libraries installed." >&2
        return 0
    fi
    echo "Libraries installed but the GTK/WebKit binding still won't load." >&2
    return 1
}
