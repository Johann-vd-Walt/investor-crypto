"""Prices + indicators endpoint tests (DB-backed)."""

import pytest
from starlette.testclient import TestClient

from app.db.session import check_db_connection
from app.main import app

client = TestClient(app)

pytestmark = pytest.mark.skipif(
    not check_db_connection()[0],
    reason="Database not reachable; skipping DB-backed API tests.",
)


def test_prices_shape_and_units():
    resp = client.get("/api/prices/BTCUSDT", params={"timeframe": "1d"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["ticker"] == "BTCUSDT"
    assert body["unit"] == "usdt"
    assert body["currency"] == "USDT"
    assert "as_of" in body and "is_delayed" in body
    assert isinstance(body["bars"], list)

    if body["bars"]:
        bar = body["bars"][-1]
        # Must serialise as a JSON number, not a Decimal string (regression).
        assert isinstance(bar["close"], (int, float))
        # Native USDT price (no cents conversion) — BTC is a large positive number.
        assert float(bar["close"]) > 0


def test_prices_unknown_ticker_404():
    assert client.get("/api/prices/ZZZZ").status_code == 404


def test_indicators_endpoint_shape():
    resp = client.get("/api/indicators/BTCUSDT", params={"names": "sma_20,rsi_14"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["ticker"] == "BTCUSDT"
    assert isinstance(body["series"], list)
