"""Walk-forward backtester (§8, §10) — realistic costs, no lookahead.

SCOPE (be honest about it): this backtests the **technical** signal only
(SMA/EMA/RSI/MACD/breakout). Macro regime and news sentiment are deliberately
EXCLUDED — we have no reliable point-in-time macro/news history, and scoring a
past date with today's values would be lookahead. So this measures the
technical edge, net of brokerage + slippage, and must be read as such.

No lookahead: at each bar i the signal uses only bars[:i+1]; the trade is then
simulated forward on bars[i+1:]. One open trade at a time per security. Trades
still open at the end of data are marked ``open_at_end`` and flagged.

Out-of-sample: metrics are computed for the full window AND for trades entered
on/after a split date (the honest headline). Long-only (BUY signals).
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal

import pandas as pd

from app.config import Settings
from app.db.models import SignalDirection
from app.signals import paper
from app.signals.engine import compute_trade_levels
from app.signals.technical import technical_score

MIN_BARS = 50


@dataclass
class BacktestTrade:
    ticker: str
    entry_datetime: datetime
    exit_datetime: datetime | None
    entry_price: Decimal   # cents
    exit_price: Decimal | None  # cents
    quantity: int
    pnl: Decimal | None    # net cents
    return_pct: float | None
    reason: str | None     # "stop" | "horizon" | "open_at_end"


@dataclass
class BacktestMetrics:
    trades: int
    wins: int
    win_rate: float | None
    avg_return_pct: float | None
    total_pnl: Decimal      # cents, net of costs
    avg_hold_days: float | None
    max_drawdown: Decimal   # cents (peak-to-trough on cumulative net P&L)
    gross_profit: Decimal = Decimal(0)   # cents
    gross_loss: Decimal = Decimal(0)     # cents (positive magnitude)
    profit_factor: float | None = None   # gross_profit / gross_loss
    expectancy: Decimal = Decimal(0)     # cents, mean P&L per trade
    reward_risk: float | None = None     # mean(return%) / stdev(return%)
    returns: list[float] = field(default_factory=list)  # per-trade return %, for robustness


@dataclass
class EquityPoint:
    on_date: date
    cumulative_pnl: Decimal  # cents


def _df(bars) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "open": [float(b.open) for b in bars],
            "high": [float(b.high) for b in bars],
            "low": [float(b.low) for b in bars],
            "close": [float(b.close) for b in bars],
            "volume": [float(b.volume) if b.volume is not None else float("nan") for b in bars],
        },
        index=[b.bar_datetime for b in bars],
    )


def walk_forward(
    *,
    ticker: str,
    bars: list,
    settings: Settings,
    costs: paper.Costs,
    min_bars: int = MIN_BARS,
) -> list[BacktestTrade]:
    """Simulate long trades from technical BUY signals over ``bars`` (asc)."""
    if len(bars) < min_bars + 1:
        return []

    df = _df(bars)
    index_of = {b.bar_datetime: i for i, b in enumerate(bars)}
    trades: list[BacktestTrade] = []

    i = min_bars - 1
    while i < len(bars):
        tech = technical_score(df.iloc[: i + 1])
        if tech.score < settings.buy_threshold:
            i += 1
            continue

        close = tech.extra.get("close")
        atr = tech.extra.get("atr")
        entry, stop, size = compute_trade_levels(
            direction=SignalDirection.BUY, close_cents=close, atr_cents=atr, settings=settings
        )
        if not (entry and stop and size and size > 0):
            i += 1
            continue

        future = [
            paper.BarLite(bar_datetime=b.bar_datetime, high=b.high, low=b.low, close=b.close)
            for b in bars[i + 1:]
        ]
        decision = paper.evaluate_exit(
            entry_datetime=bars[i].bar_datetime,
            stop_price=stop,
            horizon_days=settings.default_horizon_days,
            bars=future,
            entry_price=entry,
            trailing_pct=settings.trailing_stop_pct,
        )
        if decision is not None:
            exit_price, exit_dt, reason = decision.exit_price, decision.exit_datetime, decision.reason
            next_i = index_of[exit_dt] + 1
        else:
            exit_price, exit_dt, reason = bars[-1].close, bars[-1].bar_datetime, "open_at_end"
            next_i = len(bars)

        pnl = paper.net_pnl(entry_price=entry, exit_price=exit_price, quantity=size, costs=costs)
        notional = entry * size
        return_pct = float(pnl) / float(notional) * 100.0 if notional else None
        trades.append(
            BacktestTrade(
                ticker=ticker,
                entry_datetime=bars[i].bar_datetime,
                exit_datetime=exit_dt,
                entry_price=entry,
                exit_price=exit_price,
                quantity=size,
                pnl=pnl,
                return_pct=return_pct,
                reason=reason,
            )
        )
        i = next_i

    return trades


def summarize(trades: list[BacktestTrade]) -> tuple[BacktestMetrics, list[EquityPoint]]:
    closed = [t for t in trades if t.pnl is not None]
    n = len(closed)
    if n == 0:
        return BacktestMetrics(0, 0, None, None, Decimal(0), None, Decimal(0)), []

    wins = sum(1 for t in closed if t.pnl > 0)
    returns = [t.return_pct for t in closed if t.return_pct is not None]
    holds = [
        (t.exit_datetime.date() - t.entry_datetime.date()).days
        for t in closed
        if t.exit_datetime is not None
    ]

    gross_profit = sum((t.pnl for t in closed if t.pnl > 0), Decimal(0))
    gross_loss = -sum((t.pnl for t in closed if t.pnl < 0), Decimal(0))  # positive
    profit_factor = float(gross_profit / gross_loss) if gross_loss > 0 else None

    reward_risk = None
    if len(returns) >= 2:
        sd = statistics.pstdev(returns)
        if sd > 0:
            reward_risk = (sum(returns) / len(returns)) / sd

    # Equity curve + max drawdown on cumulative net P&L (ordered by exit).
    ordered = sorted(closed, key=lambda t: t.exit_datetime or t.entry_datetime)
    cum = Decimal(0)
    peak = Decimal(0)
    max_dd = Decimal(0)
    curve: list[EquityPoint] = []
    for t in ordered:
        cum += t.pnl or Decimal(0)
        peak = max(peak, cum)
        max_dd = min(max_dd, cum - peak)  # most negative drawdown
        if t.exit_datetime is not None:
            curve.append(EquityPoint(on_date=t.exit_datetime.date(), cumulative_pnl=cum))

    metrics = BacktestMetrics(
        trades=n,
        wins=wins,
        win_rate=wins / n,
        avg_return_pct=sum(returns) / len(returns) if returns else None,
        total_pnl=cum,
        avg_hold_days=sum(holds) / len(holds) if holds else None,
        max_drawdown=max_dd,
        gross_profit=gross_profit,
        gross_loss=gross_loss,
        profit_factor=profit_factor,
        expectancy=cum / n,
        reward_risk=reward_risk,
        returns=returns,
    )
    return metrics, curve


@dataclass
class MomentumPeriod:
    rebalance_date: date
    holdings: list[str]
    period_return_pct: float  # net of round-trip costs, equal-weighted


@dataclass
class MomentumMetrics:
    n_rebalances: int
    total_return_pct: float | None
    annualised_return_pct: float | None
    sharpe: float | None
    max_drawdown_pct: float | None
    avg_holdings: float | None
    win_rate_periods: float | None
    equity_curve: list[EquityPoint]        # normalised: cents field holds equity*10000
    returns: list[float] = field(default_factory=list)  # per-period returns (fraction), for robustness


@dataclass
class MomentumResult:
    periods: list[MomentumPeriod]
    full: MomentumMetrics
    out_of_sample: MomentumMetrics | None


def _momentum_metrics(periods: list[MomentumPeriod], rebalance_days: int) -> MomentumMetrics:
    if not periods:
        return MomentumMetrics(0, None, None, None, None, None, None, [])
    prets = [p.period_return_pct / 100.0 for p in periods]
    equity = 1.0
    peak = 1.0
    max_dd = 0.0
    curve: list[EquityPoint] = []
    for p in periods:
        equity *= (1.0 + p.period_return_pct / 100.0)
        peak = max(peak, equity)
        max_dd = min(max_dd, equity / peak - 1.0)
        curve.append(EquityPoint(on_date=p.rebalance_date, cumulative_pnl=Decimal(str(round(equity * 10000, 2)))))
    periods_per_year = 252.0 / rebalance_days
    ann = ((equity ** (periods_per_year / len(periods))) - 1.0) * 100.0 if equity > 0 else None
    sharpe = None
    if len(prets) >= 2:
        sd = statistics.pstdev(prets)
        if sd > 0:
            sharpe = (sum(prets) / len(prets)) / sd * (periods_per_year ** 0.5)
    return MomentumMetrics(
        n_rebalances=len(periods),
        total_return_pct=(equity - 1.0) * 100.0,
        annualised_return_pct=ann,
        sharpe=sharpe,
        max_drawdown_pct=max_dd * 100.0,
        avg_holdings=sum(len(p.holdings) for p in periods) / len(periods),
        win_rate_periods=sum(1 for p in prets if p > 0) / len(prets),
        equity_curve=curve,
        returns=prets,
    )


def _aligned_frames(bars_by_ticker: dict[str, list]):
    """Return (close_df, value_df) aligned on a common date index (ffilled).

    value_df = close(Rand) * volume, for the liquidity screen.
    """
    closes, values = {}, {}
    for tk, bars in bars_by_ticker.items():
        if len(bars) < 2:
            continue
        idx = [b.bar_datetime for b in bars]
        closes[tk] = pd.Series([float(b.close) for b in bars], index=idx)
        values[tk] = pd.Series(
            [
                (float(b.close) / 100.0) * (float(b.volume) if b.volume is not None else float("nan"))
                for b in bars
            ],
            index=idx,
        )
    if not closes:
        return None, None
    close_df = pd.DataFrame(closes).sort_index().ffill()
    value_df = pd.DataFrame(values).sort_index().ffill()
    return close_df, value_df


def momentum_portfolio_backtest(
    bars_by_ticker: dict[str, list],
    *,
    settings,
    top_k: int = 10,
    rebalance_days: int = 21,
    split_date: date | None = None,
) -> MomentumResult:
    """Equal-weight, long-only cross-sectional momentum, rebalanced every
    ``rebalance_days`` trading days. No lookahead: selection at date t uses only
    closes up to t; the holding return is the realised move to the next
    rebalance. Net of round-trip costs (STT on buys). ``split_date`` yields an
    out-of-sample metrics block (periods rebalanced on/after the split)."""
    close_df, value_df = _aligned_frames(bars_by_ticker)
    empty = MomentumResult([], _momentum_metrics([], rebalance_days), None)
    if close_df is None or len(close_df) < settings.momentum_lookback_days + settings.momentum_skip_days + rebalance_days + 1:
        return empty

    lookback = settings.momentum_lookback_days
    skip = settings.momentum_skip_days
    liq_look = settings.liquidity_lookback_days
    min_zar = float(settings.min_liquidity_zar)
    entry_frac = float(settings.brokerage_pct + settings.slippage_pct + settings.stt_pct) / 100.0
    exit_frac = float(settings.brokerage_pct + settings.slippage_pct) / 100.0

    dates = list(close_df.index)
    start = lookback + skip
    rebal_idx = list(range(start, len(dates) - 1, rebalance_days))

    periods: list[MomentumPeriod] = []
    for r in rebal_idx:
        next_r = min(r + rebalance_days, len(dates) - 1)
        t = dates[r]

        moms: dict[str, float] = {}
        for tk in close_df.columns:
            col = close_df[tk]
            recent = col.iloc[r - skip]
            past = col.iloc[r - skip - lookback]
            cur = col.iloc[r]
            if pd.isna(recent) or pd.isna(past) or pd.isna(cur) or past == 0:
                continue
            # Liquidity screen as-of t.
            liq = value_df[tk].iloc[max(0, r - liq_look + 1): r + 1].mean()
            if pd.isna(liq) or liq < min_zar:
                continue
            moms[tk] = recent / past - 1.0

        if not moms:
            continue
        picks = [tk for tk, _ in sorted(moms.items(), key=lambda kv: kv[1], reverse=True)[:top_k]]

        rets = []
        for tk in picks:
            entry = close_df[tk].iloc[r]
            exit_ = close_df[tk].iloc[next_r]
            if pd.isna(entry) or pd.isna(exit_) or entry == 0:
                continue
            gross = exit_ / entry - 1.0
            rets.append(gross - entry_frac - exit_frac)  # round-trip cost
        if not rets:
            continue
        periods.append(
            MomentumPeriod(
                rebalance_date=t.date(), holdings=picks,
                period_return_pct=(sum(rets) / len(rets)) * 100.0,
            )
        )

    if not periods:
        return empty

    full = _momentum_metrics(periods, rebalance_days)
    oos = None
    if split_date is not None:
        oos = _momentum_metrics([p for p in periods if p.rebalance_date >= split_date], rebalance_days)
    return MomentumResult(periods=periods, full=full, out_of_sample=oos)


def buy_and_hold_pct(bars: list) -> float | None:
    """Simple buy-and-hold % over the available bars (first close -> last close)."""
    if len(bars) < 2:
        return None
    first, last = float(bars[0].close), float(bars[-1].close)
    if first == 0:
        return None
    return (last / first - 1.0) * 100.0


@dataclass
class FoldMetrics:
    """One sequential walk-forward window's out-of-sample-style result."""
    index: int
    start: date
    end: date
    trades: int
    win_rate: float | None
    avg_return_pct: float | None
    total_pnl: Decimal      # cents
    sharpe: float | None    # per-trade
    psr: float | None       # P(true Sharpe > 0) within the fold


def walk_forward_folds(trades: list[BacktestTrade], *, n_folds: int = 4) -> list[FoldMetrics]:
    """Bucket trades into ``n_folds`` sequential time windows (by entry date) and
    summarise each. A genuine edge shows up in most folds; an overfit one lives
    in a single lucky window. Uses per-fold PSR (trials=1) as a consistency read.
    """
    from app.signals import robustness as rob

    if not trades or n_folds < 1:
        return []
    dates = [t.entry_datetime.date() for t in trades]
    start, end = min(dates), max(dates)
    total = (end - start).days or 1

    buckets: dict[int, list[BacktestTrade]] = {i: [] for i in range(n_folds)}
    for t in trades:
        di = (t.entry_datetime.date() - start).days
        idx = min(n_folds - 1, di * n_folds // (total + 1))
        buckets[idx].append(t)

    folds: list[FoldMetrics] = []
    for i in range(n_folds):
        m, _curve = summarize(buckets[i])
        r = rob.robustness(m.returns, trials=1)
        f_start = start + timedelta(days=round(i * total / n_folds))
        f_end = end if i == n_folds - 1 else start + timedelta(days=round((i + 1) * total / n_folds))
        folds.append(FoldMetrics(
            index=i + 1, start=f_start, end=f_end, trades=m.trades,
            win_rate=m.win_rate, avg_return_pct=m.avg_return_pct,
            total_pnl=m.total_pnl, sharpe=r["sharpe"], psr=r["psr"],
        ))
    return folds


def split_trades(
    trades: list[BacktestTrade], split: date | None
) -> tuple[list[BacktestTrade], list[BacktestTrade]]:
    """(in_sample, out_of_sample) by entry date. OOS = entered on/after split."""
    if split is None:
        return trades, []
    ins = [t for t in trades if t.entry_datetime.date() < split]
    oos = [t for t in trades if t.entry_datetime.date() >= split]
    return ins, oos
