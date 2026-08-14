"""Crypto market/macro endpoint tests (DB-backed): BTC + Fear & Greed."""

import pytest
from starlette.testclient import TestClient

from app.db.session import check_db_connection
from app.main import app

client = TestClient(app)

pytestmark = pytest.mark.skipif(
    not check_db_connection()[0],
    reason="Database not reachable; skipping DB-backed API tests.",
)


def test_macro_snapshot_shape():
    resp = client.get("/api/macro")
    assert resp.status_code == 200
    items = resp.json()["items"]
    codes = {i["series_code"] for i in items}

    assert {"BTC", "FNG"} <= codes
    for item in items:
        if item["available"]:
            assert item["value"] is not None
            assert item["as_of"] is not None
            # Must serialise as a JSON number, not a Decimal string (regression).
            assert isinstance(item["value"], (int, float))


def test_macro_series_and_unknown():
    ok = client.get("/api/macro/BTC")
    assert ok.status_code == 200
    assert ok.json()["series_code"] == "BTC"

    assert client.get("/api/macro/NOT_A_SERIES").status_code == 404
