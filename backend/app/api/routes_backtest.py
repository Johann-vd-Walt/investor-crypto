"""Backtest endpoint (§8). Walk-forward, cost-aware, out-of-sample."""

from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.repositories import macro as macro_repo
from app.repositories import prices as prices_repo
from app.repositories import securities as securities_repo
from app.schemas.backtest import (
    BacktestEquityPoint,
    BacktestRequest,
    BacktestResponse,
    BacktestTradeOut,
    BenchmarkOut,
    MetricsOut,
    MomentumEquityPoint,
    MomentumMetricsOut,
    MomentumRequest,
    MomentumResponse,
)
from app.schemas.prices import cents_to_rand
from app.services import settings as settings_service
from app.signals import backtest as bt
from app.signals import momentum, paper
from app.signals import robustness as rob

router = APIRouter(prefix="/api", tags=["backtest"])

_SCOPE_NOTE = (
    "Technical-signal walk-forward only (SMA/EMA/RSI/MACD/breakout). Macro regime "
    "and news sentiment are excluded — no reliable point-in-time history, and using "
    "current values on past dates would be lookahead. Net of brokerage + slippage."
)
_DISCLAIMER = (
    "Past simulated performance does not predict future results. All figures are "
    "NET OF COSTS. Read the out-of-sample column, not the full-sample one, and read "
    "the Deflated Sharpe: it is the probability the edge is real after accounting "
    "for sample size AND how many settings you tried. Below ~95% the edge is not "
    "established — a single lucky configuration is exactly what tuning produces."
)

_MAX_SAMPLE_TRADES = 100


def _metrics_out(m: bt.BacktestMetrics, account_cents: Decimal, trials: int = 1) -> MetricsOut:
    dd_pct = None
    if account_cents and account_cents != 0:
        dd_pct = float(m.max_drawdown) / float(account_cents) * 100.0
    r = rob.robustness(m.returns, trials=trials)
    return MetricsOut(
        trades=m.trades,
        wins=m.wins,
        win_rate=m.win_rate,
        avg_return_pct=m.avg_return_pct,
        total_pnl=cents_to_rand(m.total_pnl),
        avg_hold_days=m.avg_hold_days,
        max_drawdown=cents_to_rand(m.max_drawdown),
        max_drawdown_pct=dd_pct,
        profit_factor=m.profit_factor,
        expectancy=cents_to_rand(m.expectancy),
        reward_risk=m.reward_risk,
        sharpe=r["sharpe"],
        psr=r["psr"],
        deflated_sharpe=r["deflated_sharpe"],
        trials=r["trials"],
        robustness_note=r["note"],
    )


@router.post("/backtest", response_model=BacktestResponse)
def run_backtest(payload: BacktestRequest, db: Session = Depends(get_db)) -> BacktestResponse:
    settings = settings_service.get_effective_settings(db)
    if payload.overrides:
        try:
            settings = settings.model_copy(update=settings_service.coerce_overrides(payload.overrides))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    costs = paper.Costs(
        brokerage_pct=settings.brokerage_pct,
        slippage_pct=settings.slippage_pct,
        stt_pct=settings.stt_pct,
    )

    # Resolve target securities.
    if payload.tickers:
        secs = [s for t in payload.tickers if (s := securities_repo.get_by_ticker(db, t))]
    else:
        ids = prices_repo.security_ids_with_bars(db)
        secs = [s for i in ids if (s := securities_repo.get_by_id(db, i))]

    all_trades: list[bt.BacktestTrade] = []
    bars_by_sec: dict[str, list] = {}
    for sec in secs:
        bars = prices_repo.get_bars(db, security_id=sec.id)
        # Liquidity filter (Phase B): skip untradeable thin names.
        closes = [float(b.close) for b in bars]
        vols = [float(b.volume) if b.volume is not None else float("nan") for b in bars]
        if not momentum.is_liquid(
            closes, vols, min_zar=settings.min_liquidity_zar,
            lookback=settings.liquidity_lookback_days,
        ):
            continue
        bars_by_sec[sec.ticker] = bars
        all_trades.extend(bt.walk_forward(ticker=sec.ticker, bars=bars, settings=settings, costs=costs))

    account_cents = settings.account_size * Decimal(100)
    full_metrics, full_curve = bt.summarize(all_trades)
    _ins, oos = bt.split_trades(all_trades, payload.split_date)
    oos_metrics, oos_curve = bt.summarize(oos) if payload.split_date else (None, [])

    # Benchmark: buy-&-hold of the tested names + JSE Top 40 over the window.
    window_start = window_end = None
    bh = [p for bars in bars_by_sec.values() if (p := bt.buy_and_hold_pct(bars)) is not None]
    buy_hold_avg = sum(bh) / len(bh) if bh else None
    if bars_by_sec:
        starts = [bars[0].bar_datetime.date() for bars in bars_by_sec.values() if bars]
        ends = [bars[-1].bar_datetime.date() for bars in bars_by_sec.values() if bars]
        window_start, window_end = min(starts), max(ends)
    btc_pct = None
    if window_start and window_end:
        btc = macro_repo.get_series(db, series_code="BTC", start=window_start, end=window_end)
        if len(btc) >= 2 and float(btc[0].value) != 0:
            btc_pct = (float(btc[-1].value) / float(btc[0].value) - 1.0) * 100.0

    curve = oos_curve if payload.split_date else full_curve
    sample = sorted(all_trades, key=lambda t: t.entry_datetime)[-_MAX_SAMPLE_TRADES:]

    return BacktestResponse(
        tickers_tested=len(bars_by_sec),
        split_date=payload.split_date,
        full=_metrics_out(full_metrics, account_cents, payload.trials),
        out_of_sample=_metrics_out(oos_metrics, account_cents, payload.trials) if oos_metrics else None,
        benchmark=BenchmarkOut(
            window_start=window_start,
            window_end=window_end,
            buy_hold_avg_pct=buy_hold_avg,
            btc_pct=btc_pct,
        ),
        equity_curve=[
            BacktestEquityPoint(date=p.on_date, cumulative_pnl=cents_to_rand(p.cumulative_pnl))
            for p in curve
        ],
        sample_trades=[
            BacktestTradeOut(
                ticker=t.ticker,
                entry_datetime=t.entry_datetime,
                exit_datetime=t.exit_datetime,
                entry_price=cents_to_rand(t.entry_price),
                exit_price=cents_to_rand(t.exit_price),
                quantity=t.quantity,
                pnl=cents_to_rand(t.pnl),
                return_pct=t.return_pct,
                reason=t.reason,
            )
            for t in sample
        ],
        scope_note=_SCOPE_NOTE,
        disclaimer=_DISCLAIMER,
    )


_MOM_SCOPE = (
    "Equal-weight long-only cross-sectional momentum: every rebalance, hold the "
    "top-K liquid names by trailing return. Walk-forward, no lookahead, net of "
    "round-trip costs incl. STT. Compare to buy-and-hold / Top 40."
)


@router.post("/backtest/momentum", response_model=MomentumResponse)
def run_momentum_backtest(payload: MomentumRequest, db: Session = Depends(get_db)) -> MomentumResponse:
    settings = settings_service.get_effective_settings(db)
    if payload.overrides:
        try:
            settings = settings.model_copy(update=settings_service.coerce_overrides(payload.overrides))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    if payload.tickers:
        secs = [s for t in payload.tickers if (s := securities_repo.get_by_ticker(db, t))]
    else:
        ids = prices_repo.security_ids_with_bars(db)
        secs = [s for i in ids if (s := securities_repo.get_by_id(db, i))]

    bars_by_ticker = {s.ticker: prices_repo.get_bars(db, security_id=s.id) for s in secs}
    bars_by_ticker = {tk: b for tk, b in bars_by_ticker.items() if len(b) >= 2}

    result = bt.momentum_portfolio_backtest(
        bars_by_ticker, settings=settings, top_k=payload.top_k,
        rebalance_days=payload.rebalance_days, split_date=payload.split_date,
    )

    def _mm(m: bt.MomentumMetrics) -> MomentumMetricsOut:
        r = rob.robustness(m.returns, trials=payload.trials)
        return MomentumMetricsOut(
            n_rebalances=m.n_rebalances,
            total_return_pct=m.total_return_pct,
            annualised_return_pct=m.annualised_return_pct,
            sharpe=m.sharpe,
            max_drawdown_pct=m.max_drawdown_pct,
            avg_holdings=m.avg_holdings,
            win_rate_periods=m.win_rate_periods,
            psr=r["psr"],
            deflated_sharpe=r["deflated_sharpe"],
            trials=r["trials"],
            robustness_note=r["note"],
        )

    # Benchmark over the backtest window.
    window_start = window_end = None
    starts = [b[0].bar_datetime.date() for b in bars_by_ticker.values() if b]
    ends = [b[-1].bar_datetime.date() for b in bars_by_ticker.values() if b]
    if starts and ends:
        window_start, window_end = min(starts), max(ends)
    bh = [p for b in bars_by_ticker.values() if (p := bt.buy_and_hold_pct(b)) is not None]
    buy_hold_avg = sum(bh) / len(bh) if bh else None
    btc_pct = None
    if window_start and window_end:
        btc = macro_repo.get_series(db, series_code="BTC", start=window_start, end=window_end)
        if len(btc) >= 2 and float(btc[0].value) != 0:
            btc_pct = (float(btc[-1].value) / float(btc[0].value) - 1.0) * 100.0

    latest_holdings = result.periods[-1].holdings if result.periods else []

    return MomentumResponse(
        tickers_tested=len(bars_by_ticker),
        top_k=payload.top_k,
        rebalance_days=payload.rebalance_days,
        split_date=payload.split_date,
        full=_mm(result.full),
        out_of_sample=_mm(result.out_of_sample) if result.out_of_sample else None,
        benchmark=BenchmarkOut(
            window_start=window_start, window_end=window_end,
            buy_hold_avg_pct=buy_hold_avg, btc_pct=btc_pct,
        ),
        latest_holdings=latest_holdings,
        equity_curve=[
            MomentumEquityPoint(date=p.on_date, equity=(p.cumulative_pnl / Decimal(10000)))
            for p in result.full.equity_curve
        ],
        scope_note=_MOM_SCOPE,
        disclaimer=_DISCLAIMER,
    )
