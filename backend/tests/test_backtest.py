"""Phase 8: backtester (no-lookahead, cost-aware) + settings service tests."""

from datetime import date, datetime, timedelta
from decimal import Decimal

from app.config import Settings
from app.signals import backtest as bt
from app.signals import paper

COSTS = paper.Costs(brokerage_pct=Decimal("0.1"), slippage_pct=Decimal("0.1"))


class _Bar:
    def __init__(self, dt, o, h, low, c, v=1000.0):
        self.bar_datetime, self.open, self.high, self.low, self.close, self.volume = (
            dt, Decimal(str(o)), Decimal(str(h)), Decimal(str(low)), Decimal(str(c)), v
        )


def _uptrend_bars(n=120, start=10000.0, step=80.0):
    base = datetime(2025, 1, 1)
    bars = []
    for i in range(n):
        c = start + step * i
        bars.append(_Bar(base + timedelta(days=i), c, c + 50, c - 50, c))
    return bars


def test_backtest_generates_trades_in_uptrend():
    s = Settings(_env_file=None)
    trades = bt.walk_forward(ticker="TEST", bars=_uptrend_bars(), settings=s, costs=COSTS)
    assert len(trades) > 0
    # Every trade has an entry before its exit, and P&L is net (costs applied).
    for t in trades:
        assert t.exit_datetime is None or t.exit_datetime >= t.entry_datetime
        assert t.pnl is not None
        assert t.quantity > 0


def test_backtest_no_lookahead_short_series():
    s = Settings(_env_file=None)
    # Fewer than min_bars+1 -> no trades (can't score without history).
    assert bt.walk_forward(ticker="T", bars=_uptrend_bars(n=40), settings=s, costs=COSTS) == []


def test_backtest_one_open_trade_at_a_time():
    s = Settings(_env_file=None)
    trades = bt.walk_forward(ticker="T", bars=_uptrend_bars(), settings=s, costs=COSTS)
    # Trades must not overlap (next entry after previous exit).
    ordered = sorted(trades, key=lambda t: t.entry_datetime)
    for a, b in zip(ordered, ordered[1:]):
        assert a.exit_datetime is not None
        assert b.entry_datetime >= a.exit_datetime


def test_summarize_and_split():
    s = Settings(_env_file=None)
    trades = bt.walk_forward(ticker="T", bars=_uptrend_bars(), settings=s, costs=COSTS)
    metrics, curve = bt.summarize(trades)
    assert metrics.trades == len([t for t in trades if t.pnl is not None])
    assert metrics.win_rate is not None
    assert len(curve) >= 1

    split = trades[len(trades) // 2].entry_datetime.date()
    ins, oos = bt.split_trades(trades, split)
    assert all(t.entry_datetime.date() < split for t in ins)
    assert all(t.entry_datetime.date() >= split for t in oos)


def test_momentum_portfolio_picks_strongest_and_runs():
    s = Settings(_env_file=None).model_copy(update={
        "min_liquidity_zar": Decimal("0"),
        "momentum_lookback_days": 20,
        "momentum_skip_days": 2,
    })
    base = datetime(2025, 1, 1)
    n = 120

    def series(step):
        return [
            _Bar(base + timedelta(days=i), 10000 + step * i, 10000 + step * i + 50,
                 10000 + step * i - 50, 10000 + step * i)
            for i in range(n)
        ]

    bars_by_ticker = {
        "UP": series(120),     # strong uptrend -> best momentum
        "FLAT": series(0),
        "DOWN": series(-40),
    }
    res = bt.momentum_portfolio_backtest(
        bars_by_ticker, settings=s, top_k=1, rebalance_days=10
    )
    assert res.full.n_rebalances > 0
    # The uptrend name should dominate the picks.
    picks = [h for p in res.periods for h in p.holdings]
    assert picks.count("UP") >= picks.count("DOWN")
    assert res.full.total_return_pct is not None


def test_momentum_portfolio_oos_split():
    s = Settings(_env_file=None).model_copy(update={
        "min_liquidity_zar": Decimal("0"), "momentum_lookback_days": 20, "momentum_skip_days": 2,
    })
    base = datetime(2025, 1, 1)
    bars = {
        "UP": [_Bar(base + timedelta(days=i), 10000 + 100 * i, 10000 + 100 * i + 50, 10000 + 100 * i - 50, 10000 + 100 * i) for i in range(120)],
        "DOWN": [_Bar(base + timedelta(days=i), 20000 - 40 * i, 20000 - 40 * i + 50, 20000 - 40 * i - 50, 20000 - 40 * i) for i in range(120)],
    }
    res = bt.momentum_portfolio_backtest(bars, settings=s, top_k=1, rebalance_days=10, split_date=date(2025, 3, 1))
    assert res.out_of_sample is not None
    assert res.out_of_sample.n_rebalances <= res.full.n_rebalances
    assert all(p.rebalance_date >= date(2025, 1, 1) for p in res.periods)


def test_momentum_portfolio_empty_when_too_short():
    s = Settings(_env_file=None)
    res = bt.momentum_portfolio_backtest({"A": _uptrend_bars(n=30)}, settings=s, top_k=1)
    assert res.full.n_rebalances == 0


def test_costs_reduce_backtest_pnl():
    s = Settings(_env_file=None)
    bars = _uptrend_bars()
    free = paper.Costs(brokerage_pct=Decimal("0"), slippage_pct=Decimal("0"))
    with_costs = bt.walk_forward(ticker="T", bars=bars, settings=s, costs=COSTS)
    without = bt.walk_forward(ticker="T", bars=bars, settings=s, costs=free)
    # Same signals/trades, but net P&L must be lower once costs apply.
    assert bt.summarize(with_costs)[0].total_pnl < bt.summarize(without)[0].total_pnl
