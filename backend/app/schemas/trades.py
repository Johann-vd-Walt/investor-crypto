"""Trade journal + tax-summary schemas (§11).

Prices/fees are entered and returned in RAND (presentation), stored in cents.
The tax summary is record-keeping only, not advice (§15).
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.db.models import TradeSide
from app.schemas.common import DecimalAsFloat


class TradeCreate(BaseModel):
    ticker: str = Field(..., min_length=1, max_length=12)
    side: TradeSide
    quantity: int = Field(..., gt=0)
    price: Decimal = Field(..., ge=0, description="Per-share price in RAND")
    fees: Decimal = Field(default=Decimal(0), ge=0, description="Total fees in RAND")
    trade_datetime: datetime
    linked_signal_id: int | None = None
    rationale: str | None = Field(default=None, max_length=1000)


class TradeOut(BaseModel):
    id: int
    security_id: int
    ticker: str
    side: TradeSide
    quantity: int
    price: DecimalAsFloat   # Rand
    fees: DecimalAsFloat    # Rand
    trade_datetime: datetime
    linked_signal_id: int | None
    rationale: str | None
    created_at: datetime


class TradeListResponse(BaseModel):
    items: list[TradeOut]
    total: int
    limit: int
    offset: int


class DisposalOut(BaseModel):
    ticker: str
    sell_datetime: datetime
    quantity: int
    proceeds: DecimalAsFloat     # Rand, net of sell fees
    base_cost: DecimalAsFloat    # Rand, incl. buy fees
    gain: DecimalAsFloat         # Rand
    unmatched_quantity: int


class TaxSummaryResponse(BaseModel):
    tax_year: int
    period_start: date
    period_end: date
    disposals: list[DisposalOut]
    total_proceeds: DecimalAsFloat
    total_base_cost: DecimalAsFloat
    total_realised_gain: DecimalAsFloat
    disclaimer: str
