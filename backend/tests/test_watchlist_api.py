"""Phase 1 API tests for securities + watchlist.

These run against the configured database (they require MySQL up and the seed
to have run). They clean up any watchlist entry they create.
"""

import pytest
from starlette.testclient import TestClient

from app.db.session import check_db_connection
from app.main import app

client = TestClient(app)

pytestmark = pytest.mark.skipif(
    not check_db_connection()[0],
    reason="Database not reachable; skipping DB-backed API tests.",
)


def test_list_securities_returns_seeded_rows() -> None:
    resp = client.get("/api/securities", params={"limit": 5})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] >= 1
    assert len(body["items"]) <= 5
    assert {"ticker", "name", "currency"} <= set(body["items"][0])


def test_get_security_by_ticker_and_404() -> None:
    assert client.get("/api/securities/BTCUSDT").status_code == 200
    assert client.get("/api/securities/ZZZZ").status_code == 404


def test_watchlist_add_list_delete_roundtrip() -> None:
    # Ensure a clean slate (a prior interrupted run may have left the entry).
    for e in client.get("/api/watchlist").json():
        if e["security"]["ticker"] == "BTCUSDT":
            client.delete(f"/api/watchlist/{e['id']}")

    # Add
    add = client.post("/api/watchlist", json={"ticker": "BTCUSDT", "notes": "test"})
    assert add.status_code == 201, add.text
    entry_id = add.json()["id"]
    try:
        assert add.json()["security"]["ticker"] == "BTCUSDT"

        # Duplicate is rejected
        dup = client.post("/api/watchlist", json={"ticker": "BTCUSDT"})
        assert dup.status_code == 409

        # Unknown ticker rejected
        assert client.post("/api/watchlist", json={"ticker": "ZZZZ"}).status_code == 404

        # List includes it
        listing = client.get("/api/watchlist")
        assert listing.status_code == 200
        assert any(e["id"] == entry_id for e in listing.json())
    finally:
        # Delete (cleanup)
        assert client.delete(f"/api/watchlist/{entry_id}").status_code == 204

    # Deleting again 404s
    assert client.delete(f"/api/watchlist/{entry_id}").status_code == 404
