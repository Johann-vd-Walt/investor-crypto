"""Phase 7: FIFO realised-gains tax logic (deterministic, §14) + journal
endpoints (DB-backed)."""

from datetime import datetime
from decimal import Decimal

import pytest
from sqlalchemy import delete
from starlette.testclient import TestClient

from app import tax
from app.db.models import Trade
from app.db.session import SessionLocal, check_db_connection
from app.main import app

client = TestClient(app)


def _t(side, qty, price, fees, dt):
    return tax.TradeRow(
        security_id=1, ticker="BTCUSDT", side=side, quantity=qty,
        price=Decimal(price), fees=Decimal(fees), trade_datetime=dt,
    )


def test_tax_year_bounds():
    start, end = tax.tax_year_bounds(2026)
    assert start.isoformat() == "2025-03-01"
    assert end.isoformat() == "2026-02-28"


def test_fifo_realised_gain_with_fees():
    # Buy 100 @ 10000c (fee 500c), sell 100 @ 12000c (fee 500c) inside FY2026.
    trades = [
        _t("BUY", 100, "10000", "500", datetime(2025, 6, 1)),
        _t("SELL", 100, "12000", "500", datetime(2025, 9, 1)),
    ]
    s = tax.realised_gains_for_tax_year(trades, 2026)
    assert len(s.disposals) == 1
    d = s.disposals[0]
    # proceeds = 100*12000 - 500 = 1,199,500
    assert d.proceeds == Decimal("1199500")
    # base cost = 100*(10000 + 5) = 1,000,500
    assert d.base_cost == Decimal("1000500")
    assert d.gain == Decimal("199000")
    assert s.total_gain == Decimal("199000")


def test_fifo_partial_lots_and_year_filter():
    trades = [
        _t("BUY", 50, "10000", "0", datetime(2024, 5, 1)),   # prior year lot
        _t("BUY", 50, "12000", "0", datetime(2025, 4, 1)),
        _t("SELL", 60, "13000", "0", datetime(2025, 10, 1)),  # in FY2026
    ]
    s = tax.realised_gains_for_tax_year(trades, 2026)
    d = s.disposals[0]
    # FIFO: 50 @10000 + 10 @12000 = 500000 + 120000 = 620000 base
    assert d.base_cost == Decimal("620000")
    assert d.proceeds == Decimal("780000")  # 60*13000
    assert d.gain == Decimal("160000")


def test_oversold_flags_unmatched():
    trades = [
        _t("BUY", 10, "10000", "0", datetime(2025, 6, 1)),
        _t("SELL", 15, "11000", "0", datetime(2025, 7, 1)),
    ]
    s = tax.realised_gains_for_tax_year(trades, 2026)
    assert s.disposals[0].unmatched_quantity == 5


def test_sells_outside_year_excluded():
    trades = [
        _t("BUY", 10, "10000", "0", datetime(2025, 6, 1)),
        _t("SELL", 10, "11000", "0", datetime(2027, 6, 1)),  # FY2028, not 2026
    ]
    assert tax.realised_gains_for_tax_year(trades, 2026).disposals == []


# --- Endpoints (DB-backed) ---

pytestmark = pytest.mark.skipif(not check_db_connection()[0], reason="DB not reachable.")


def test_journal_create_list_delete_and_units():
    created_id = None
    try:
        # price in RAND; stored as cents; returned as Rand.
        resp = client.post("/api/trades", json={
            "ticker": "BTCUSDT", "side": "BUY", "quantity": 10, "price": 855.70,
            "fees": 20.00, "trade_datetime": "2025-06-01T10:00:00",
            "rationale": "test entry",
        })
        assert resp.status_code == 201, resp.text
        body = resp.json()
        created_id = body["id"]
        assert body["ticker"] == "BTCUSDT"
        assert body["price"] == 855.70  # round-trips through cents cleanly
        assert isinstance(body["price"], (int, float))

        listing = client.get("/api/trades")
        assert listing.status_code == 200
        assert any(t["id"] == created_id for t in listing.json()["items"])
    finally:
        if created_id is not None:
            assert client.delete(f"/api/trades/{created_id}").status_code == 204

    assert client.post("/api/trades", json={
        "ticker": "ZZZZ", "side": "BUY", "quantity": 1, "price": 1,
        "trade_datetime": "2025-06-01T10:00:00",
    }).status_code == 404


def test_tax_summary_endpoint_roundtrip():
    """Buy+sell in FY2026, check realised gain in Rand, then clean up."""
    ids = []
    db = SessionLocal()
    try:
        r1 = client.post("/api/trades", json={
            "ticker": "BTCUSDT", "side": "BUY", "quantity": 100, "price": 100.0,
            "fees": 5.0, "trade_datetime": "2025-06-01T10:00:00"})
        r2 = client.post("/api/trades", json={
            "ticker": "BTCUSDT", "side": "SELL", "quantity": 100, "price": 120.0,
            "fees": 5.0, "trade_datetime": "2025-09-01T10:00:00"})
        ids = [r1.json()["id"], r2.json()["id"]]

        summary = client.get("/api/trades/tax-summary", params={"tax_year": 2026}).json()
        assert summary["tax_year"] == 2026
        assert summary["period_start"] == "2025-03-01"
        ours = [d for d in summary["disposals"] if d["ticker"] == "BTCUSDT"]
        assert ours, "expected an BTCUSDT disposal in FY2026"
        # proceeds 100*120 - 5 = R11,995; base 100*100 + 5 = R10,005; gain R1,990
        d = ours[-1]
        assert d["proceeds"] == 11995.0
        assert d["base_cost"] == 10005.0
        assert d["gain"] == 1990.0
        assert summary["disclaimer"]
    finally:
        for tid in ids:
            client.delete(f"/api/trades/{tid}")
        db.close()
