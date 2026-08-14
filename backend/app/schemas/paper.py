"""Paper-trading response schemas (§11).

Prices/P&L stored in cents, returned in RAND. Win rate is only reported once
enough closed trades exist (``has_edge_data``) — otherwise it is null and the
UI must say the edge is not yet measured (§10 honesty requirement).
"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel

from app.db.models import PaperTradeStatus
from app.schemas.common import DecimalAsFloat


class PaperTradeOut(BaseModel):
    id: int
    security_id: int
    ticker: str
    entry_datetime: datetime
    entry_price: DecimalAsFloat        # Rand
    quantity: int
    stop_price: DecimalAsFloat | None  # Rand
    exit_datetime: datetime | None
    exit_price: DecimalAsFloat | None  # Rand
    pnl: DecimalAsFloat | None         # Rand, net of costs
    unrealized_pnl: DecimalAsFloat | None  # Rand, gross (open trades only)
    status: PaperTradeStatus


class EquityPointOut(BaseModel):
    date: date
    cumulative_pnl: DecimalAsFloat  # Rand


class PaperPerformanceResponse(BaseModel):
    sample_size: int
    wins: int
    min_sample: int
    has_edge_data: bool          # sample_size >= min_sample
    win_rate: DecimalAsFloat | None
    avg_return_pct: DecimalAsFloat | None
    total_pnl: DecimalAsFloat    # Rand, net of costs
    equity_curve: list[EquityPointOut]
