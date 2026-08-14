"""Phase 6: paper-trade exit logic + cost-aware P&L (deterministic, §14)
and the performance endpoints (DB-backed, seeded)."""

from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import delete
from starlette.testclient import TestClient

from app.db.models import PaperTrade, PaperTradeStatus
from app.db.session import SessionLocal, check_db_connection
from app.main import app
from app.repositories import securities as securities_repo
from app.signals import paper

client = TestClient(app)

COSTS = paper.Costs(brokerage_pct=Decimal("0.1"), slippage_pct=Decimal("0.1"))


def _bar(day, high, low, close):
    return paper.BarLite(
        bar_datetime=datetime(2026, 7, day), high=Decimal(high), low=Decimal(low), close=Decimal(close)
    )


# --- Exit logic ---

def test_exit_on_stop_hit():
    entry = datetime(2026, 7, 1)
    bars = [_bar(2, 10200, 9900, 10100), _bar(3, 10100, 9400, 9500)]  # day 3 low breaches 9500
    d = paper.evaluate_exit(entry_datetime=entry, stop_price=Decimal("9500"), horizon_days=10, bars=bars)
    assert d is not None and d.reason == "stop"
    assert d.exit_price == Decimal("9500")
    assert d.exit_datetime == datetime(2026, 7, 3)


def test_exit_on_horizon():
    entry = datetime(2026, 7, 1)
    bars = [_bar(1 + i, 10000, 9900, 10000 + i) for i in range(1, 12)]
    d = paper.evaluate_exit(entry_datetime=entry, stop_price=Decimal("1"), horizon_days=10, bars=bars)
    assert d is not None and d.reason == "horizon"
    # First bar at/after 10 days from entry (2026-07-11).
    assert d.exit_datetime == datetime(2026, 7, 11)


def test_still_open_when_neither_triggers():
    entry = datetime(2026, 7, 1)
    bars = [_bar(2, 10200, 9990, 10100), _bar(3, 10300, 10000, 10250)]
    d = paper.evaluate_exit(entry_datetime=entry, stop_price=Decimal("9000"), horizon_days=10, bars=bars)
    assert d is None


# --- Cost-aware P&L ---

def test_net_pnl_subtracts_costs():
    # Buy 100 @ 10000c, sell @ 11000c. Gross = 100*1000 = 100000c.
    gross = Decimal("100000")
    net = paper.net_pnl(entry_price=Decimal("10000"), exit_price=Decimal("11000"), quantity=100, costs=COSTS)
    # Costs = (10000*100 + 11000*100) * 0.002 = 2100000 * 0.002 = 4200c.
    assert net == gross - Decimal("4200")
    assert net < gross  # honesty: costs always reduce P&L


def test_net_pnl_can_turn_small_gain_negative():
    net = paper.net_pnl(entry_price=Decimal("10000"), exit_price=Decimal("10010"), quantity=100, costs=COSTS)
    assert net < 0  # tiny gross gain wiped out by costs


def test_stt_charged_on_buy_side_only():
    base = paper.Costs(brokerage_pct=Decimal("0"), slippage_pct=Decimal("0"))
    with_stt = paper.Costs(brokerage_pct=Decimal("0"), slippage_pct=Decimal("0"), stt_pct=Decimal("0.25"))
    # Buy 100 @ 10000c = 1,000,000c notional. STT 0.25% = 2500c, buy side only.
    n0 = paper.net_pnl(entry_price=Decimal("10000"), exit_price=Decimal("11000"), quantity=100, costs=base)
    n1 = paper.net_pnl(entry_price=Decimal("10000"), exit_price=Decimal("11000"), quantity=100, costs=with_stt)
    assert n0 - n1 == Decimal("2500")  # exactly the STT on the entry notional


def test_trailing_stop_locks_in_gains():
    entry = datetime(2026, 7, 1)
    # Rises to 12000 then pulls back; a 10% trailing stop should exit on the drop.
    bars = [
        _bar(2, 11000, 10800, 11000),
        _bar(3, 12000, 11800, 12000),   # high-water close 12000 -> trail 10800
        _bar(4, 12000, 10700, 10750),   # low 10700 < 10800 -> trailing stop hit
    ]
    d = paper.evaluate_exit(
        entry_datetime=entry, entry_price=Decimal("10000"), stop_price=Decimal("9000"),
        horizon_days=30, bars=bars, trailing_pct=Decimal("10"),
    )
    assert d is not None and d.reason == "trailing_stop"
    assert d.exit_price == Decimal("10800")  # 10% below the 12000 high-water


# --- Performance endpoint (DB-backed, seeded) ---

pytestmark = pytest.mark.skipif(not check_db_connection()[0], reason="DB not reachable.")


@pytest.fixture
def seeded_paper_trades():
    db = SessionLocal()
    sec = securities_repo.get_by_ticker(db, "BTCUSDT")
    created = []
    try:
        base = datetime(2026, 6, 1)
        # 3 closed trades: 2 winners, 1 loser.
        specs = [(Decimal("10000"), Decimal("11000"), Decimal("100000")),
                 (Decimal("10000"), Decimal("9500"), Decimal("-50000")),
                 (Decimal("20000"), Decimal("21000"), Decimal("100000"))]
        for i, (ep, xp, pnl) in enumerate(specs):
            t = PaperTrade(
                signal_id=None, security_id=sec.id,
                entry_datetime=base + timedelta(days=i),
                entry_price=ep, quantity=100, stop_price=None,
                exit_datetime=base + timedelta(days=i + 5), exit_price=xp,
                pnl=pnl, status=PaperTradeStatus.CLOSED,
            )
            db.add(t)
            db.flush()
            created.append(t.id)
        db.commit()
        yield created
    finally:
        if created:
            db.execute(delete(PaperTrade).where(PaperTrade.id.in_(created)))
            db.commit()
        db.close()


def test_paper_performance_endpoint(seeded_paper_trades):
    body = client.get("/api/paper/performance").json()
    assert body["sample_size"] >= 3
    assert body["wins"] >= 2
    # Fewer than MIN_SAMPLE closed trades -> win_rate withheld (honest).
    assert body["has_edge_data"] == (body["sample_size"] >= body["min_sample"])
    assert isinstance(body["total_pnl"], (int, float))
    assert len(body["equity_curve"]) >= 3


def test_paper_trades_endpoint(seeded_paper_trades):
    body = client.get("/api/paper/trades").json()
    assert isinstance(body, list)
    ours = [t for t in body if t["id"] in seeded_paper_trades]
    assert len(ours) == 3
    assert all(t["status"] == "CLOSED" for t in ours)
    # pnl returned in native quote currency (no conversion).
    win = next(t for t in ours if t["pnl"] and t["pnl"] > 0)
    assert win["pnl"] == 100000.0
