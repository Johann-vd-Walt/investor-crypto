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
    quantity: DecimalAsFloat
    stop_price: DecimalAsFloat | None
    live_price: DecimalAsFloat | None
    cost_basis: DecimalAsFloat
    venue: str
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
    mode: str                    # 'paper' | 'live'
    dry_run: bool
    max_order_usd: DecimalAsFloat
    daily_cap_usd: DecimalAsFloat
    daily_spent_usd: DecimalAsFloat
    luno_configured: bool         # keys present in server env
    initial_cash: DecimalAsFloat
    cash: DecimalAsFloat
    realized_pnl: DecimalAsFloat
    equity: DecimalAsFloat
    return_pct: DecimalAsFloat
    open_positions: int
    started_at: datetime | None
    last_tick_at: datetime | None


class LunoBalance(BaseModel):
    asset: str
    balance: float
    available: float
    reserved: float


class LunoStatusOut(BaseModel):
    configured: bool
    error: str | None
    balances: list[LunoBalance]


class BotResponse(BaseModel):
    status: BotStatusOut
    positions: list[BotPositionOut]
    events: list[BotEventOut]
    equity_curve: list[BotEquityPoint]
    note: str


class ModeUpdate(BaseModel):
    mode: str


class DryRunUpdate(BaseModel):
    dry_run: bool


class CapsUpdate(BaseModel):
    max_order_usd: DecimalAsFloat | None = None
    daily_cap_usd: DecimalAsFloat | None = None
