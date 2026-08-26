"""Backtest request/response schemas (§8)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.common import DecimalAsFloat


class BacktestRequest(BaseModel):
    tickers: list[str] | None = Field(default=None, description="Default: all securities with price history")
    split_date: date | None = Field(default=None, description="Out-of-sample trades entered on/after this date")
    overrides: dict[str, Any] = Field(default_factory=dict, description="One-off tunable overrides (not persisted)")
    trials: int = Field(default=1, ge=1, le=100000, description="How many strategy configs you've tried — used to DEFLATE the Sharpe for selection bias. Be honest: 1 if this is the first run.")


class MetricsOut(BaseModel):
    trades: int
    wins: int
    win_rate: DecimalAsFloat | None
    avg_return_pct: DecimalAsFloat | None
    total_pnl: DecimalAsFloat        # Rand, net of costs
    avg_hold_days: DecimalAsFloat | None
    max_drawdown: DecimalAsFloat     # Rand
    max_drawdown_pct: DecimalAsFloat | None   # vs account size
    profit_factor: DecimalAsFloat | None
    expectancy: DecimalAsFloat       # Rand per trade
    reward_risk: DecimalAsFloat | None  # mean/stdev of per-trade returns
    # --- Robustness (Tier 3): is the edge real, or short-sample + tuning luck? ---
    sharpe: DecimalAsFloat | None       # per-trade Sharpe
    psr: DecimalAsFloat | None          # Probabilistic Sharpe: P(true Sharpe > 0), 0..1
    deflated_sharpe: DecimalAsFloat | None  # PSR deflated for `trials` configs, 0..1
    trials: int                          # how many configs the deflation assumed
    robustness_note: str


class BenchmarkOut(BaseModel):
    window_start: date | None
    window_end: date | None
    buy_hold_avg_pct: DecimalAsFloat | None   # avg buy-&-hold of tested assets
    btc_pct: DecimalAsFloat | None            # Bitcoin buy-&-hold over the window


class BacktestEquityPoint(BaseModel):
    date: date
    cumulative_pnl: DecimalAsFloat   # Rand


class BacktestTradeOut(BaseModel):
    ticker: str
    entry_datetime: datetime
    exit_datetime: datetime | None
    entry_price: DecimalAsFloat      # Rand
    exit_price: DecimalAsFloat | None  # Rand
    quantity: DecimalAsFloat
    pnl: DecimalAsFloat | None       # Rand, net
    return_pct: DecimalAsFloat | None
    reason: str | None


class MomentumRequest(BaseModel):
    tickers: list[str] | None = Field(default=None, description="Default: all securities with price history")
    top_k: int = Field(default=10, ge=1, le=50)
    rebalance_days: int = Field(default=21, ge=5, le=120)
    split_date: date | None = Field(default=None, description="Out-of-sample: periods rebalanced on/after this date")
    overrides: dict[str, Any] = Field(default_factory=dict)
    trials: int = Field(default=1, ge=1, le=100000, description="How many configs you've tried — deflates the Sharpe for selection bias. 1 if this is the first run.")


class MomentumEquityPoint(BaseModel):
    date: date
    equity: DecimalAsFloat  # normalised, starts at 1.0


class MomentumMetricsOut(BaseModel):
    n_rebalances: int
    total_return_pct: DecimalAsFloat | None
    annualised_return_pct: DecimalAsFloat | None
    sharpe: DecimalAsFloat | None            # annualised
    max_drawdown_pct: DecimalAsFloat | None
    avg_holdings: DecimalAsFloat | None
    win_rate_periods: DecimalAsFloat | None
    # --- Robustness (Tier 3): is the edge real, or short-sample + tuning luck? ---
    psr: DecimalAsFloat | None               # P(true per-period Sharpe > 0), 0..1
    deflated_sharpe: DecimalAsFloat | None   # PSR deflated for `trials` configs, 0..1
    trials: int
    robustness_note: str


class MomentumResponse(BaseModel):
    tickers_tested: int
    top_k: int
    rebalance_days: int
    split_date: date | None
    full: MomentumMetricsOut
    out_of_sample: MomentumMetricsOut | None
    benchmark: BenchmarkOut
    latest_holdings: list[str]
    equity_curve: list[MomentumEquityPoint]  # full-sample equity growth
    scope_note: str
    disclaimer: str


class FoldMetricsOut(BaseModel):
    index: int
    start: date
    end: date
    trades: int
    win_rate: DecimalAsFloat | None
    avg_return_pct: DecimalAsFloat | None
    total_pnl: DecimalAsFloat        # Rand, net
    sharpe: DecimalAsFloat | None
    psr: DecimalAsFloat | None


class BacktestResponse(BaseModel):
    tickers_tested: int
    split_date: date | None
    full: MetricsOut
    out_of_sample: MetricsOut | None
    benchmark: BenchmarkOut
    equity_curve: list[BacktestEquityPoint]  # OOS if split given, else full
    sample_trades: list[BacktestTradeOut]
    walk_forward: list[FoldMetricsOut]       # sequential time folds (overfitting check)
    scope_note: str
    disclaimer: str
