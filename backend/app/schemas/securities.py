"""Pydantic response/request schemas for securities."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class SecurityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ticker: str
    isin: str | None
    name: str
    sector: str | None
    currency: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


class SecurityListResponse(BaseModel):
    items: list[SecurityOut]
    total: int
    limit: int
    offset: int
