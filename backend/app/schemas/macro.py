"""Macro response schemas.

Macro values are in native units (USD, ZAR/USD, index points), NOT cents.
Each snapshot item carries ``as_of`` so the UI can show freshness (§12).
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel

from app.schemas.common import DecimalAsFloat


class MacroObservationOut(BaseModel):
    observation_date: date
    value: DecimalAsFloat
    unit: str | None
    source: str | None


class MacroSnapshotItem(BaseModel):
    series_code: str
    label: str
    available: bool
    value: DecimalAsFloat | None = None
    unit: str | None = None
    as_of: date | None = None
    source: str | None = None
    note: str | None = None  # e.g. why a series is unavailable


class MacroSnapshotResponse(BaseModel):
    items: list[MacroSnapshotItem]


class MacroSeriesResponse(BaseModel):
    series_code: str
    label: str
    unit: str | None
    source: str | None
    observations: list[MacroObservationOut]
