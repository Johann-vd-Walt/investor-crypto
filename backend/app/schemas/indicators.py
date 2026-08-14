"""Indicator response schemas.

Reads the ``indicator_values`` cache. That cache is populated by the
``compute_indicators`` job in Phase 5; until then this endpoint returns an
empty series (honest — it does not fabricate values).
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from app.schemas.common import DecimalAsFloat


class IndicatorPoint(BaseModel):
    bar_datetime: datetime
    value: DecimalAsFloat | None


class IndicatorSeries(BaseModel):
    indicator: str
    points: list[IndicatorPoint]


class IndicatorsResponse(BaseModel):
    ticker: str
    timeframe: str
    series: list[IndicatorSeries]
