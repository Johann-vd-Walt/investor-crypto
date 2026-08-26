"""Paper-trade simulation logic (§10) — pure and deterministic (§14).

Simulates long paper trades opened from BUY signals: exit on a stop hit or at
the signal horizon, whichever comes first, and compute P&L **net of realistic
costs** (brokerage + slippage). A cost-free simulation would overstate the
edge, which the spec forbids as the headline number.

All prices are in cents (ZAc); P&L is returned in cents.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass(frozen=True)
class Costs:
    brokerage_pct: Decimal       # per side, % of notional
    slippage_pct: Decimal        # per side, % of notional
    stt_pct: Decimal = Decimal("0")  # SA Securities Transfer Tax — BUY side only

    @property
    def per_side_fraction(self) -> Decimal:
        return (self.brokerage_pct + self.slippage_pct) / Decimal(100)

    @property
    def buy_only_fraction(self) -> Decimal:
        return self.stt_pct / Decimal(100)


@dataclass(frozen=True)
class BarLite:
    bar_datetime: datetime
    high: Decimal
    low: Decimal
    close: Decimal


@dataclass(frozen=True)
class ExitDecision:
    exit_datetime: datetime
    exit_price: Decimal
    reason: str  # "stop" | "horizon"


def evaluate_exit(
    *,
    entry_datetime: datetime,
    stop_price: Decimal | None,
    horizon_days: int,
    bars: list[BarLite],
    entry_price: Decimal | None = None,
    trailing_pct: Decimal = Decimal("0"),
) -> ExitDecision | None:
    """Return the exit for a long trade, or None if still open.

    Walks bars strictly AFTER entry in date order. Within a bar, a stop hit
    (low <= effective stop) takes priority over the horizon. The horizon
    triggers on the first bar at/after ``horizon_days`` from entry, exiting at
    that bar's close.

    If ``trailing_pct`` > 0, the stop ratchets up to ``trailing_pct`` % below the
    highest close seen since entry (never below the initial ``stop_price``). To
    avoid intrabar lookahead, the trailing level for a bar uses only closes up to
    the PRIOR bar; the current bar's close updates the high-water mark afterward.
    """
    trail_frac = trailing_pct / Decimal(100) if trailing_pct else Decimal(0)
    high_water = entry_price  # may be None; seeded so trailing works from entry

    for bar in sorted(bars, key=lambda b: b.bar_datetime):
        if bar.bar_datetime <= entry_datetime:
            continue

        eff_stop = stop_price
        trailing_hit = False
        if trail_frac > 0 and high_water is not None:
            trail_level = high_water * (Decimal(1) - trail_frac)
            if eff_stop is None or trail_level > eff_stop:
                eff_stop = trail_level
                trailing_hit = True

        if eff_stop is not None and bar.low <= eff_stop:
            reason = "trailing_stop" if trailing_hit else "stop"
            return ExitDecision(bar.bar_datetime, eff_stop, reason)

        if (bar.bar_datetime.date() - entry_datetime.date()).days >= horizon_days:
            return ExitDecision(bar.bar_datetime, bar.close, "horizon")

        if high_water is None or bar.close > high_water:
            high_water = bar.close

    return None


def _costs(notional_in: Decimal, notional_out: Decimal, costs: Costs) -> Decimal:
    """Brokerage+slippage on both sides, plus STT on the buy side only."""
    per_side = (notional_in + notional_out) * costs.per_side_fraction
    buy_side = notional_in * costs.buy_only_fraction
    return per_side + buy_side


def net_pnl(
    *,
    entry_price: Decimal,
    exit_price: Decimal,
    quantity: Decimal,
    costs: Costs,
) -> Decimal:
    """Net P&L in cents = gross - brokerage/slippage (both sides) - STT (buy)."""
    gross = (exit_price - entry_price) * quantity
    total_costs = _costs(entry_price * quantity, exit_price * quantity, costs)
    return gross - total_costs


def unrealized_pnl(*, entry_price: Decimal, current_price: Decimal, quantity: Decimal) -> Decimal:
    """Gross mark-to-market for an open trade (cents). Costs applied on close."""
    return (current_price - entry_price) * quantity
