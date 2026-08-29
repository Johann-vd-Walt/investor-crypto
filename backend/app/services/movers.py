"""Market movers for the tradeable universe.

- top_movers: today's % move (live price vs last daily close) for every coin,
  flagged for whether it's tradeable on Luno. Uses the app's own price data +
  Binance live prices — keyless, all coins.
- most_bought: recent buying pressure on Luno from the public trades feed
  (is_buy volume) for the 11 Luno USDT pairs. Luno has no "most bought" API, so
  this approximates it from the recent trade window. Keyless.

Both are cached briefly to avoid hammering the APIs.
"""

from __future__ import annotations

import logging
import time
from decimal import Decimal, InvalidOperation

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.bot.engine import fetch_live_prices
from app.brokers.mapping import app_base, is_tradeable, to_luno_pair
from app.config import get_settings
from app.db.models import PriceBar, Security

logger = logging.getLogger("app.services.movers")

_LUNO_TRADES = "https://api.luno.com/api/1/trades"
_HEADERS = {"User-Agent": "Mozilla/5.0"}
_cache: dict = {}


def top_movers(db: Session, *, ttl: int = 60) -> list[dict]:
    now = time.time()
    cached = _cache.get("tm")
    if cached and now - cached[0] < ttl:
        return cached[1]

    sub = (
        select(PriceBar.security_id, func.max(PriceBar.bar_datetime).label("mx"))
        .group_by(PriceBar.security_id).subquery()
    )
    rows = db.execute(
        select(PriceBar.security_id, PriceBar.close).join(
            sub, (PriceBar.security_id == sub.c.security_id) & (PriceBar.bar_datetime == sub.c.mx)
        )
    ).all()
    last_close = {sid: Decimal(str(c)) for sid, c in rows}
    secs = {s.id: s for s in db.scalars(select(Security).where(Security.is_active.is_(True)))}
    tickers = [secs[sid].ticker for sid in last_close if sid in secs]
    live = fetch_live_prices(tickers, get_settings().binance_base_url)

    out: list[dict] = []
    for sid, lc in last_close.items():
        s = secs.get(sid)
        px = live.get(s.ticker) if s else None
        if s is None or lc <= 0 or px is None:
            continue
        out.append({
            "ticker": s.ticker, "name": s.name,
            "last_close": float(lc), "live_price": float(px),
            "change_pct": float((px / lc - 1) * 100),
            "luno": is_tradeable(s.ticker),
        })
    out.sort(key=lambda x: x["change_pct"], reverse=True)
    _cache["tm"] = (now, out)
    return out


def _luno_trades(pair: str) -> list[dict]:
    try:
        r = httpx.get(_LUNO_TRADES, params={"pair": pair}, headers=_HEADERS, timeout=15.0)
        r.raise_for_status()
        return r.json().get("trades", []) or []
    except httpx.HTTPError as exc:
        logger.warning("luno trades %s failed: %s", pair, exc)
        return []


def most_bought(db: Session, *, ttl: int = 300) -> list[dict]:
    now = time.time()
    cached = _cache.get("mb")
    if cached and now - cached[0] < ttl:
        return cached[1]

    # tradeable coins present in our universe -> Luno pairs
    pairs: dict[str, str] = {}  # luno_pair -> app ticker
    for s in db.scalars(select(Security).where(Security.is_active.is_(True))):
        p = to_luno_pair(s.ticker)
        if p:
            pairs[p] = s.ticker

    out: list[dict] = []
    for pair, ticker in pairs.items():
        trs = _luno_trades(pair)
        buy = Decimal(0); sell = Decimal(0)
        for t in trs:
            try:
                v = Decimal(str(t.get("volume", "0")))
            except (InvalidOperation, TypeError):
                continue
            if t.get("is_buy"):
                buy += v
            else:
                sell += v
        total = buy + sell
        if total <= 0:
            continue
        out.append({
            "ticker": ticker, "pair": pair, "base": app_base(ticker),
            "buy_vol": float(buy), "sell_vol": float(sell),
            "buy_pct": float(buy / total * 100), "trades": len(trs),
        })
    out.sort(key=lambda x: x["buy_pct"], reverse=True)
    _cache["mb"] = (now, out)
    return out
