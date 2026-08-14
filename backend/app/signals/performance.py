"""Measured performance of past signals via paper trades (§10).

Confidence shown next to a signal comes from the engine's OWN measured historical
hit rate — never a black-box number (§8). Until closed paper trades exist
(Phase 6), there is no measured edge and confidence is ``None`` (honest).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import PaperTrade, PaperTradeStatus

# Minimum closed trades before we report a hit rate at all.
MIN_SAMPLE = 10


@dataclass
class EquityPoint:
    on_date: date
    cumulative_pnl: Decimal  # cents


@dataclass
class Performance:
    sample_size: int
    wins: int
    win_rate: float | None       # 0..1, None if sample too small
    avg_return_pct: float | None  # mean per-trade return %, None if none
    total_pnl: Decimal = Decimal(0)  # cents, net of costs
    equity_curve: list[EquityPoint] = field(default_factory=list)


def measured_performance(db: Session) -> Performance:
    """Aggregate closed paper trades into win rate, avg return, equity curve."""
    rows = db.execute(
        select(
            PaperTrade.pnl, PaperTrade.entry_price, PaperTrade.quantity,
            PaperTrade.exit_datetime,
        )
        .where(PaperTrade.status == PaperTradeStatus.CLOSED, PaperTrade.pnl.is_not(None))
        .order_by(PaperTrade.exit_datetime)
    ).all()

    n = len(rows)
    if n == 0:
        return Performance(sample_size=0, wins=0, win_rate=None, avg_return_pct=None)

    wins = 0
    returns: list[float] = []
    total = Decimal(0)
    curve: list[EquityPoint] = []
    for pnl, entry, qty, exit_dt in rows:
        if pnl is not None and pnl > 0:
            wins += 1
        cost = (entry or Decimal(0)) * (qty or 0)
        if cost:
            returns.append(float(pnl) / float(cost) * 100.0)
        total += pnl or Decimal(0)
        if exit_dt is not None:
            curve.append(EquityPoint(on_date=exit_dt.date(), cumulative_pnl=total))

    avg_return = sum(returns) / len(returns) if returns else None
    win_rate = wins / n if n >= MIN_SAMPLE else None
    return Performance(
        sample_size=n, wins=wins, win_rate=win_rate, avg_return_pct=avg_return,
        total_pnl=total, equity_curve=curve,
    )


def confidence_from_performance(perf: Performance) -> Decimal | None:
    """Map a measured win rate to a signal confidence (0..1). None if unknown."""
    if perf.win_rate is None:
        return None
    return Decimal(str(round(perf.win_rate, 4)))
