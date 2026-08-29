"""Schemas for market movers (top movers + most-bought-on-Luno)."""

from __future__ import annotations

from pydantic import BaseModel


class Mover(BaseModel):
    ticker: str
    name: str
    last_close: float
    live_price: float
    change_pct: float
    luno: bool          # tradeable on Luno in USDT


class MostBought(BaseModel):
    ticker: str
    pair: str
    base: str
    buy_vol: float
    sell_vol: float
    buy_pct: float      # % of recent traded volume that was buys
    trades: int


class MoversResponse(BaseModel):
    top_movers: list[Mover]
    most_bought: list[MostBought]
    note: str
