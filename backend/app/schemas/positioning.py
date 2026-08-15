"""Schemas for the derivatives / positioning endpoints (Tier 1)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class PositioningSignal(BaseModel):
    metric: str            # funding | open_interest | long_short_pos | taker_ratio
    label: str             # short human headline
    detail: str            # one-line plain-language explanation
    value: float | None    # the latest raw value, if numeric
    percentile: float | None  # 0..1 percentile of the latest value in its window, if applicable
    tone: str              # bull | bear | warn | neutral
    sample: int            # number of historical points backing this


class PositioningSnapshot(BaseModel):
    ticker: str
    name: str
    as_of: datetime | None
    available: bool        # False if no futures data (e.g. host geo-blocked / no perp)
    signals: list[PositioningSignal]
    note: str


class PositioningListResponse(BaseModel):
    count: int
    items: list[PositioningSnapshot]
