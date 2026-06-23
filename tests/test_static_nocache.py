"""NoCacheStaticFiles must always serve fresh assets (priority: medium).

After an in-place upgrade, the embedded WebKit window / browser must never
serve a stale app.js or a 304. These tests pin that contract.
"""
from fastapi.testclient import TestClient

from sessionhub.app import app

client = TestClient(app)


def test_static_asset_has_no_cache_header():
    r = client.get("/app.js")
    assert r.status_code == 200
    assert r.headers["cache-control"] == "no-cache, no-store, must-revalidate"


def test_static_asset_never_returns_304():
    # A conditional request that would normally yield 304 must still be 200.
    r = client.get("/style.css", headers={"If-Modified-Since": "Wed, 01 Jan 2031 00:00:00 GMT"})
    assert r.status_code == 200


def test_missing_static_asset_returns_404_without_crashing():
    r = client.get("/does-not-exist-12345.js")
    assert r.status_code == 404
