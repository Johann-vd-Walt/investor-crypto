"""Schemas for the copy-trading crowd-consensus endpoint (Tier 4)."""

from __future__ import annotations

from pydantic import BaseModel


class CoinConsensus(BaseModel):
    ticker: str | None      # our symbol if the coin maps to our universe, else None
    inst: str               # OKX instId, e.g. BTC-USDT-SWAP
    longs: int              # # of tracked lead traders net long
    shorts: int             # # net short
    traders: int            # total holding it
    net_bias: float         # (longs - shorts) / traders, -1..1
    lean: str               # "long" | "short" | "split"


class ConsensusResponse(BaseModel):
    source: str
    traders_sampled: int
    as_of_cache_age_s: int
    available: bool
    items: list[CoinConsensus]
    caveat: str
