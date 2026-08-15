"""Build a crowd-consensus from OKX lead-trader positions (Tier 4).

Aggregates how many top lead traders are net long vs short each coin. Cached
in-process for a few minutes (single worker) to avoid hammering OKX on every
page load. This is LOW-CONFIDENCE context — see the caveat string.
"""

from __future__ import annotations

import logging
import time

from sqlalchemy.orm import Session

from app.providers.okx_copytrading import OkxCopyTradingProvider
from app.repositories import securities as securities_repo
from app.schemas.consensus import CoinConsensus, ConsensusResponse

logger = logging.getLogger("app.services.consensus")

_CACHE_TTL = 900  # 15 minutes
_cache: dict = {"ts": 0.0, "payload": None}

CAVEAT = (
    "Low-confidence context only. Leaderboards suffer survivorship bias (you see "
    "this month's lucky survivors), latency (the move is often gone by the time a "
    "position shows), and manipulation. This is NOT a signal to copy — the app "
    "never trades for you."
)


def _inst_to_ticker(inst_id: str, known: dict[str, str]) -> str | None:
    # BTC-USDT-SWAP -> BTCUSDT (only if it's in our universe)
    parts = inst_id.split("-")
    if len(parts) >= 2:
        candidate = f"{parts[0]}{parts[1]}".upper()
        return known.get(candidate)
    return None


def _direction(pos: dict) -> str | None:
    side = (pos.get("posSide") or "").lower()
    if side == "long":
        return "long"
    if side == "short":
        return "short"
    if side == "net":
        try:
            return "long" if float(pos.get("subPos") or 0) > 0 else "short"
        except (TypeError, ValueError):
            return None
    return None


def build_consensus(db: Session, *, limit: int = 12, force: bool = False) -> ConsensusResponse:
    now = time.time()
    if not force and _cache["payload"] is not None and (now - _cache["ts"]) < _CACHE_TTL:
        payload: ConsensusResponse = _cache["payload"]
        return payload.model_copy(update={"as_of_cache_age_s": int(now - _cache["ts"])})

    provider = OkxCopyTradingProvider()
    known = {s.ticker.upper(): s.ticker for s in securities_repo.list_securities(db, limit=1000)[0]}

    agg: dict[str, dict] = {}  # inst -> {longs, shorts, traders}
    sampled = 0
    try:
        leaders = provider.get_lead_traders(limit=limit)
    except Exception as exc:  # noqa: BLE001
        logger.warning("consensus: lead-trader fetch failed: %s", exc)
        leaders = []

    for lead in leaders:
        uc = lead.get("uniqueCode")
        if not uc:
            continue
        try:
            positions = provider.get_positions(uc)
        except Exception as exc:  # noqa: BLE001
            logger.warning("consensus: positions failed for %s: %s", uc, exc)
            continue
        sampled += 1
        seen: set[tuple[str, str]] = set()
        for pos in positions:
            inst = pos.get("instId")
            direction = _direction(pos)
            if not inst or direction is None:
                continue
            # Count each trader at most once per (coin, direction).
            key = (inst, direction)
            if key in seen:
                continue
            seen.add(key)
            slot = agg.setdefault(inst, {"longs": 0, "shorts": 0, "traders": 0})
            if direction == "long":
                slot["longs"] += 1
            else:
                slot["shorts"] += 1

    items: list[CoinConsensus] = []
    for inst, slot in agg.items():
        traders = slot["longs"] + slot["shorts"]
        if traders == 0:
            continue
        net = (slot["longs"] - slot["shorts"]) / traders
        lean = "long" if net > 0.2 else "short" if net < -0.2 else "split"
        items.append(
            CoinConsensus(
                ticker=_inst_to_ticker(inst, known), inst=inst,
                longs=slot["longs"], shorts=slot["shorts"], traders=traders,
                net_bias=round(net, 3), lean=lean,
            )
        )
    # Most-held first, then strongest lean.
    items.sort(key=lambda c: (c.traders, abs(c.net_bias)), reverse=True)

    payload = ConsensusResponse(
        source="okx_copytrading", traders_sampled=sampled, as_of_cache_age_s=0,
        available=bool(items), items=items, caveat=CAVEAT,
    )
    _cache["ts"] = now
    _cache["payload"] = payload
    return payload
