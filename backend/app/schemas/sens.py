"""SENS announcement response schemas (Phase D)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class SensOut(BaseModel):
    id: int
    security_id: int | None
    ticker: str | None
    source: str
    url: str
    headline: str
    summary: str | None
    category: str | None
    published_at: datetime | None


class SensListResponse(BaseModel):
    ticker: str | None
    count: int
    items: list[SensOut]
