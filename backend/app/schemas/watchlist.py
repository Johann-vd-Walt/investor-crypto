"""Pydantic schemas for the watchlist."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.securities import SecurityOut


class WatchlistCreate(BaseModel):
    ticker: str = Field(..., min_length=1, max_length=12)
    notes: str | None = Field(default=None, max_length=500)


class WatchlistItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    added_at: datetime
    notes: str | None
    security: SecurityOut
