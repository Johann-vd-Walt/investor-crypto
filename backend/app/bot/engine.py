"""Real-time PAPER trading bot.

Simulates a long-only portfolio against LIVE Binance prices, on a continuous
tick loop. It is a paper EXECUTION layer on top of the signals the engine already
generates: each tick it (1) marks open positions to the live price and exits on
stop/horizon, (2) opens simulated positions for fresh actionable BUY signals it
hasn't acted on, subject to cash + position caps, and (3) records equity.

IMPORTANT: no real orders, no exchange API keys, no real money — ever. This
exists so you can watch the strategy trade in real time and see whether it makes
or loses money before risking a cent. Given the backtests (Deflated Sharpe ~22%,
buy-and-hold wins), expect it to underperform holding BTC.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from decimal import Decimal

import httpx
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import (
    BotEquity, BotEvent, BotPosition, BotState, Security, Signal,
    SignalDirection, SignalStatus,
)
from app.db.session import SessionLocal
from app.services import settings as settings_service

logger = logging.getLogger("app.bot")

_EQUITY_RETENTION_DAYS = 7
_EVENT_RETENTION_DAYS = 30
_SIGNAL_MAX_AGE_DAYS = 2


# --------------------------------------------------------------- live prices ---
def fetch_live_prices(symbols: list[str], base_url: str) -> dict[str, Decimal]:
    """Current price per symbol from Binance ticker/price (batch, keyless)."""
    if not symbols:
        return {}
    url = f"{base_url.rstrip('/')}/api/v3/ticker/price"
    try:
        resp = httpx.get(url, params={"symbols": json.dumps(sorted(set(symbols)))}, timeout=15.0)
        resp.raise_for_status()
        out: dict[str, Decimal] = {}
        for row in resp.json():
            try:
                out[row["symbol"].upper()] = Decimal(str(row["price"]))
            except Exception:  # noqa: BLE001
                continue
        return out
    except httpx.HTTPError as exc:
        logger.warning("bot: live price fetch failed: %s", exc)
        return {}


# ------------------------------------------------------------------- state -----
def get_state(db: Session) -> BotState | None:
    return db.get(BotState, 1)


def ensure_state(db: Session) -> BotState:
    st = db.get(BotState, 1)
    if st is None:
        settings = settings_service.get_effective_settings(db)
        cash = Decimal(settings.account_size)
        st = BotState(id=1, enabled=False, tick_seconds=60,
                      initial_cash=cash, cash=cash, realized_pnl=Decimal(0))
        db.add(st)
        db.commit()
    return st


def _log(db: Session, kind: str, detail: str, *, ticker: str | None = None, equity: Decimal | None = None) -> None:
    db.add(BotEvent(kind=kind, ticker=ticker, detail=detail, equity=equity))


def start(db: Session) -> BotState:
    st = ensure_state(db)
    st.enabled = True
    if st.started_at is None:
        st.started_at = datetime.utcnow()
    _log(db, "start", "Bot enabled — simulating against live prices.")
    db.commit()
    return st


def stop(db: Session) -> BotState:
    st = ensure_state(db)
    st.enabled = False
    _log(db, "stop", "Bot disabled.")
    db.commit()
    return st


def reset(db: Session) -> BotState:
    """Flatten the paper portfolio and start fresh from initial cash."""
    st = ensure_state(db)
    db.execute(delete(BotPosition))
    db.execute(delete(BotEquity))
    st.cash = st.initial_cash
    st.realized_pnl = Decimal(0)
    st.last_equity = None
    st.started_at = datetime.utcnow() if st.enabled else None
    _log(db, "info", f"Portfolio reset to ${st.initial_cash:.0f} paper cash.")
    db.commit()
    return st


# -------------------------------------------------------------------- tick -----
def tick(db: Session) -> dict:
    st = get_state(db)
    if st is None or not st.enabled:
        return {"skipped": "disabled"}

    settings = settings_service.get_effective_settings(db)
    now = datetime.utcnow()
    entry_frac = float(settings.brokerage_pct + settings.slippage_pct + settings.stt_pct) / 100.0
    exit_frac = float(settings.brokerage_pct + settings.slippage_pct) / 100.0

    open_pos = list(db.scalars(select(BotPosition).where(BotPosition.status == "OPEN")).all())
    acted = {sid for sid in db.scalars(
        select(BotPosition.signal_id).where(BotPosition.signal_id.is_not(None))
    ).all()}
    since = now - timedelta(days=_SIGNAL_MAX_AGE_DAYS)
    sigs = list(db.scalars(
        select(Signal).where(
            Signal.direction == SignalDirection.BUY,
            Signal.status == SignalStatus.OPEN,
            Signal.generated_at >= since,
            Signal.suggested_entry.is_not(None),
            Signal.suggested_size.is_not(None),
        ).order_by(Signal.generated_at.desc())
    ).all())

    sec_ids = {p.security_id for p in open_pos} | {s.security_id for s in sigs}
    id_to_ticker = {
        s.id: s.ticker for s in db.scalars(select(Security).where(Security.id.in_(sec_ids))).all()
    } if sec_ids else {}
    prices = fetch_live_prices(list(id_to_ticker.values()), get_settings().binance_base_url)

    summary = {"closed": 0, "opened": 0, "skipped": 0}

    # 1. Manage open positions against live prices.
    held: set[int] = set()
    for p in open_pos:
        tk = id_to_ticker.get(p.security_id)
        px = prices.get(tk) if tk else None
        if px is None:
            held.add(p.security_id)
            continue
        reason = None
        if p.stop_price is not None and px <= p.stop_price:
            reason = "stop"
        elif (now - p.entry_datetime).days >= p.horizon_days:
            reason = "horizon"
        if reason:
            proceeds = px * p.quantity * Decimal(str(1 - exit_frac))
            pnl = proceeds - p.cost_basis
            p.status, p.exit_datetime, p.exit_price, p.pnl, p.exit_reason = "CLOSED", now, px, pnl, reason
            st.cash += proceeds
            st.realized_pnl += pnl
            summary["closed"] += 1
            _log(db, "close", f"{reason} exit {p.quantity} @ {px:.4f}, P&L ${pnl:.2f}", ticker=tk)
        else:
            held.add(p.security_id)

    # 2. Open fresh actionable BUYs the bot hasn't taken.
    n_open = len(held)
    for s in sigs:
        if s.id in acted or s.security_id in held:
            continue
        tk = id_to_ticker.get(s.security_id)
        px = prices.get(tk) if tk else None
        if px is None:
            continue
        if n_open >= settings.max_open_positions:
            continue
        size = int(s.suggested_size or 0)
        if size <= 0:
            continue
        cost = px * size * Decimal(str(1 + entry_frac))
        if st.cash < cost:
            summary["skipped"] += 1
            continue
        db.add(BotPosition(
            security_id=s.security_id, signal_id=s.id, entry_datetime=now,
            entry_price=px, quantity=size, stop_price=s.suggested_stop,
            horizon_days=s.horizon_days, cost_basis=cost, status="OPEN",
        ))
        st.cash -= cost
        held.add(s.security_id)
        acted.add(s.id)
        n_open += 1
        summary["opened"] += 1
        stop_txt = f", stop {s.suggested_stop:.4f}" if s.suggested_stop is not None else ""
        _log(db, "open", f"BUY {size} @ {px:.4f}{stop_txt}", ticker=tk)

    # 3. Mark-to-market equity.
    equity = st.cash
    for p in db.scalars(select(BotPosition).where(BotPosition.status == "OPEN")).all():
        tk = id_to_ticker.get(p.security_id)
        mark = prices.get(tk) if tk else None
        equity += p.quantity * (mark if mark is not None else p.entry_price)
    st.last_equity = equity
    st.last_tick_at = now
    db.add(BotEquity(ts=now, equity=equity, cash=st.cash))

    # Heartbeat + housekeeping (cheap, low-frequency).
    if now.minute % 15 == 0:
        _log(db, "info", f"Heartbeat — equity ${equity:.2f}, {n_open} open, cash ${st.cash:.2f}", equity=equity)
    if now.minute == 0:
        db.execute(delete(BotEquity).where(BotEquity.ts < now - timedelta(days=_EQUITY_RETENTION_DAYS)))
        db.execute(delete(BotEvent).where(BotEvent.created_at < now - timedelta(days=_EVENT_RETENTION_DAYS)))

    db.commit()
    summary["equity"] = float(equity)
    return summary


def safe_tick() -> None:
    """Scheduler entry point — one tick, never raises."""
    db = SessionLocal()
    try:
        result = tick(db)
        if result.get("opened") or result.get("closed"):
            logger.info("bot tick: %s", result)
    except Exception:  # noqa: BLE001 — a bot failure must never kill the scheduler
        db.rollback()
        logger.exception("bot tick crashed")
        try:
            _log(db, "error", "Tick failed — see server logs.")
            db.commit()
        except Exception:  # noqa: BLE001
            db.rollback()
    finally:
        db.close()
