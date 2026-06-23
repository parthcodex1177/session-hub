"""Tests for the standalone-binary packaging seams (priority: high).

These guard the bits that only matter once frozen by PyInstaller — the static
path resolver, the port fallback, and the contract that the browser/standalone
import graph never pulls in the native-GUI stack.
"""
import socket
import sys
from pathlib import Path

from sessionhub import app as app_module
from sessionhub.standalone import _pick_port


def test_static_dir_uses_meipass_when_frozen(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    assert app_module._static_dir() == tmp_path / "sessionhub" / "static"


def test_static_dir_uses_source_path_when_not_frozen(monkeypatch):
    monkeypatch.delattr(sys, "_MEIPASS", raising=False)
    d = app_module._static_dir()
    assert d.name == "static"
    assert (d / "index.html").exists()


def test_pick_port_returns_default_when_free(monkeypatch):
    # config.PORT is almost certainly free in the test env.
    assert _pick_port() == app_module.config.PORT


def test_pick_port_falls_back_when_default_taken(monkeypatch):
    # Hold config.PORT, then _pick_port must return a different, usable port.
    held = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    held.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
    try:
        held.bind((app_module.config.HOST, app_module.config.PORT))
        port = _pick_port()
        assert port != app_module.config.PORT
        assert isinstance(port, int) and port > 0
    except OSError:
        # Port couldn't be bound (rare CI race) — skip rather than flake.
        import pytest

        pytest.skip("could not bind config.PORT to exercise fallback")
    finally:
        held.close()


def test_standalone_import_graph_has_no_native_gui():
    # The browser/standalone path must not import webview or gi — that's what
    # lets pywebview be an optional [native] extra and keeps the binary lean.
    import sessionhub.app  # noqa: F401
    import sessionhub.standalone  # noqa: F401

    assert "webview" not in sys.modules
    assert "gi" not in sys.modules
