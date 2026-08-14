"""Price response schemas.

Crypto prices are stored and returned in the **quote currency** (e.g. USDT) at
native precision — there is no cents convention. The two converter functions are
kept (call sites across the API use them) but are now identity passthroughs.
Every response carries ``as_of`` and ``is_delayed`` for freshness.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel

from app.schemas.common import DecimalAsFloat


def cents_to_rand(value: Decimal | None) -> Decimal | None:
    """Storage -> display. Native quote price passthrough (no conversion)."""
    return value


def rand_to_cents(value: Decimal | None) -> Decimal | None:
    """Display -> storage. Native quote price passthrough (no conversion)."""
    return Decimal(value) if value is not None else None


class PriceBarOut(BaseModel):
    bar_datetime: datetime
    open: DecimalAsFloat   # quote currency (e.g. USDT)
    high: DecimalAsFloat
    low: DecimalAsFloat
    close: DecimalAsFloat
    adj_close: DecimalAsFloat | None
    volume: int | None


class PriceSeriesResponse(BaseModel):
    ticker: str
    timeframe: str
    currency: str = "USDT"
    unit: str = "usdt"
    as_of: datetime | None
    is_delayed: bool
    source: str | None
    bars: list[PriceBarOut]
