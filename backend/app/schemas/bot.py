"""Schemas for the real-time paper trading bot."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from app.schemas.common import DecimalAsFloat


class BotPositionOut(BaseModel):
    ticker: str
    name: str
    entry_datetime: datetime
    entry_price: DecimalAsFloat
    quantity: int
    stop_price: DecimalAsFloat | None
    live_price: DecimalAsFloat | None
    cost_basis: DecimalAsFloat
    market_value: DecimalAsFloat | None
    unrealized_pnl: DecimalAsFloat | None
    unrealized_pct: DecimalAsFloat | None


class BotEventOut(BaseModel):
    created_at: datetime
    kind: str
    ticker: str | None
    detail: str
    equity: DecimalAsFloat | None


class BotEquityPoint(BaseModel):
    ts: datetime
    equity: DecimalAsFloat


class BotStatusOut(BaseModel):
    enabled: bool
    tick_seconds: int
    initial_cash: DecimalAsFloat
    cash: DecimalAsFloat
    realized_pnl: DecimalAsFloat
    equity: DecimalAsFloat
    return_pct: DecimalAsFloat
    open_positions: int
    started_at: datetime | None
    last_tick_at: datetime | None


class BotResponse(BaseModel):
    status: BotStatusOut
    positions: list[BotPositionOut]
    events: list[BotEventOut]
    equity_curve: list[BotEquityPoint]
    note: str
