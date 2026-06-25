"""Python 3.8 compatibility regression guards.

The supported floor was lowered from 3.10 to 3.8 (for pipx install on old
systems). The mechanism: every sessionhub module starts with
``from __future__ import annotations`` and FastAPI route params use
``typing.Optional[str]`` instead of the 3.10-only ``str | None`` syntax.

FastAPI resolves route-handler annotations at runtime via get_type_hints, so a
``X | Y`` union in a route param would raise TypeError on 3.8 even though the
``from __future__`` import makes module-level annotations lazy. These tests fail
loudly if a future contributor reintroduces that 3.10-only syntax.
"""
import ast
import importlib
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from sessionhub import app as app_module
from sessionhub import config, db

# Every shipped module that must import cleanly under the 3.8 floor.
_SHIPPED_MODULES = [
    "sessionhub.app",
    "sessionhub.parse_claude",
    "sessionhub.parse_antigravity",
    "sessionhub.db",
    "sessionhub.scanner",
    "sessionhub.active",
    "sessionhub.pricing",
    "sessionhub.config",
    "sessionhub.resume",
    "sessionhub.standalone",
]

_SESSIONHUB_DIR = Path(config.__file__).resolve().parent
_SOURCE_FILES = sorted(p for p in _SESSIONHUB_DIR.glob("*.py") if p.name != "__init__.py")

# FastAPI decorator attributes whose presence marks a function as a route
# handler — its param annotations are resolved at runtime by FastAPI.
_ROUTE_METHODS = {"get", "post", "delete", "put", "patch"}


@pytest.mark.parametrize("module_name", _SHIPPED_MODULES)
def test_every_shipped_module_imports_without_error(module_name):
    # A 3.10-only construct evaluated at import time (e.g. a runtime union)
    # would raise here on the 3.8 floor.
    assert importlib.import_module(module_name) is not None


def test_desktop_module_imports_when_native_extra_present():
    # desktop.py imports the optional pywebview/native extra lazily, but guard
    # anyway so a missing extra skips rather than fails the compat suite.
    try:
        module = importlib.import_module("sessionhub.desktop")
    except ImportError:
        pytest.skip("sessionhub.desktop requires the optional native extra")
    assert module is not None


@pytest.mark.parametrize(
    "source_path", _SOURCE_FILES, ids=lambda p: p.name
)
def test_every_module_declares_future_annotations(source_path):
    # `from __future__ import annotations` is what makes module-level
    # annotations lazy on 3.8 — its removal is a silent regression.
    tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
    has_future_annotations = any(
        isinstance(node, ast.ImportFrom)
        and node.module == "__future__"
        and any(alias.name == "annotations" for alias in node.names)
        for node in tree.body
    )
    assert has_future_annotations, (
        f"{source_path.name} is missing `from __future__ import annotations`"
    )


def _is_route_handler(func_node):
    """True if any decorator on the function is an ``app.<method>(...)`` call."""
    for decorator in func_node.decorator_list:
        # Route decorators are calls: @app.get("/path", ...)
        target = decorator.func if isinstance(decorator, ast.Call) else decorator
        if isinstance(target, ast.Attribute) and target.attr in _ROUTE_METHODS:
            return True
    return False


def _binor_param_annotations(func_node):
    """Return names of params whose annotation uses ``X | Y`` (BinOp/BitOr)."""
    args = func_node.args
    all_args = (
        list(args.posonlyargs)
        + list(args.args)
        + list(args.kwonlyargs)
        + ([args.vararg] if args.vararg else [])
        + ([args.kwarg] if args.kwarg else [])
    )
    offenders = []
    for arg in all_args:
        ann = arg.annotation
        if isinstance(ann, ast.BinOp) and isinstance(ann.op, ast.BitOr):
            offenders.append(arg.arg)
    return offenders


@pytest.mark.parametrize(
    "source_path", _SOURCE_FILES, ids=lambda p: p.name
)
def test_no_route_handler_uses_pep604_union_param_annotation(source_path):
    # FastAPI evaluates route-param annotations at runtime via get_type_hints;
    # an `X | Y` union there raises TypeError on 3.8. This is the real
    # regression vector the review asked us to guard. Use Optional[X] instead.
    tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
    violations = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and _is_route_handler(node):
            for param in _binor_param_annotations(node):
                violations.append(f"{node.name}({param})")
    assert not violations, (
        f"{source_path.name}: route handler param(s) use 3.8-incompatible "
        f"PEP 604 union syntax (use typing.Optional instead): {violations}"
    )


@pytest.fixture
def smoke_client(tmp_path, monkeypatch):
    """Hermetic TestClient: tmp DB + stubbed active_sessions.

    Mirrors tests/test_app_sessions.py — point app._connect at a tmp sqlite
    file built from the real db.DDL, and stub active_sessions so the request
    never reads real ~/.claude data or the real ~/.local index.db.
    """
    db_path = tmp_path / "index.db"
    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    con.executescript(db.DDL)
    con.commit()
    con.close()

    def _connect():
        c = sqlite3.connect(str(db_path))
        c.row_factory = sqlite3.Row
        return c

    monkeypatch.setattr(app_module, "_connect", _connect)
    monkeypatch.setattr(app_module, "active_sessions", lambda: {})
    return TestClient(app_module.app)


def test_sessions_endpoint_constructs_and_responds_200(smoke_client):
    # A successful response proves FastAPI resolved the route's Optional[str]
    # param annotations at app-construction time on the running interpreter.
    resp = smoke_client.get("/api/sessions")
    assert resp.status_code == 200


def test_sessions_endpoint_resolves_optional_query_params_200(smoke_client):
    # tool/q/date_from are the Optional[str] query params that would have been
    # `str | None` before the 3.8 port — exercising them proves get_type_hints
    # resolved them rather than raising at request time.
    resp = smoke_client.get(
        "/api/sessions",
        params={"tool": "claude", "q": "hello", "date_from": "2026-06-01"},
    )
    assert resp.status_code == 200
