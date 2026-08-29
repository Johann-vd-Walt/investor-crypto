"""Trading bot endpoints — PAPER by default, optional LIVE on Luno.

Live trading is gated: real orders require mode=live, dry_run=off, Luno keys in
the server env, and the per-order/daily caps. Switching mode/dry-run is done here
but the app never arms live-real on its own.
"""

from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.bot import engine
from app.bot import performance as bot_perf
from app.db.models import BotEquity, BotEvent, BotPosition, Security
from app.db.session import get_db
from app.schemas.bot import (
    BotEquityPoint, BotEventOut, BotPerformanceOut, BotPositionOut, BotResponse,
    BotStatusOut, CapsUpdate, DryRunUpdate, LunoStatusOut, ModeUpdate, VenueStats,
)

router = APIRouter(prefix="/api/bot", tags=["bot"])

_NOTE_PAPER = (
    "PAPER bot: simulated fills against live prices — no real orders, no real money. "
    "The backtests show no established edge (Deflated Sharpe ~22%) and buy-and-hold "
    "beat the strategy, so treat a rising curve with scepticism."
)
_NOTE_LIVE_DRY = (
    "LIVE · DRY-RUN: connected to Luno for pricing/balances but placing NO real "
    "orders — it logs the exact order it would send. Flip dry-run off to trade for real."
)
_NOTE_LIVE_REAL = (
    "⚠ LIVE · REAL MONEY: this bot is placing real orders on your Luno account, "
    "capped per-order and per-day. The strategy has no proven edge — expect losses. "
    "Kill switch: set mode back to Paper, or Stop."
)


def _build_response(db: Session) -> BotResponse:
    st = engine.ensure_state(db)
    live = st.mode == "live"
    broker = engine.get_broker() if live else None
    luno_ok = engine.get_broker() is not None
    venue = "luno" if live else "paper"

    open_pos = list(db.scalars(
        select(BotPosition).where(BotPosition.status == "OPEN", BotPosition.venue == venue)
    ).all())
    sec_by_id = {
        s.id: s for s in db.scalars(
            select(Security).where(Security.id.in_([p.security_id for p in open_pos]))
        ).all()
    } if open_pos else {}
    tickers = [sec_by_id[p.security_id].ticker for p in open_pos if p.security_id in sec_by_id]
    prices = engine.live_price_map(tickers, live=live, broker=broker)

    positions: list[BotPositionOut] = []
    equity = Decimal(st.cash)
    for p in open_pos:
        sec = sec_by_id.get(p.security_id)
        if sec is None:
            continue
        live = prices.get(sec.ticker)
        mv = (live * p.quantity) if live is not None else None
        upnl = (mv - p.cost_basis) if mv is not None else None
        upct = (float(upnl) / float(p.cost_basis) * 100.0) if (upnl is not None and p.cost_basis) else None
        equity += mv if mv is not None else (p.entry_price * p.quantity)
        positions.append(BotPositionOut(
            ticker=sec.ticker, name=sec.name, entry_datetime=p.entry_datetime,
            entry_price=p.entry_price, quantity=p.quantity, stop_price=p.stop_price,
            live_price=live, cost_basis=p.cost_basis, venue=p.venue, market_value=mv,
            unrealized_pnl=upnl, unrealized_pct=upct,
        ))

    # Venue-specific realised P&L (live shows ONLY real Luno closes — not paper,
    # and not dry-run simulations).
    realized = bot_perf.venue_stats(db, venue, real_only=live)["total_pnl"]
    # Baseline for return %. In live mode, anchor to the real account: capture it
    # now if it hasn't been set (so return reads ~0% from the moment you start
    # tracking live, not -97% against the paper starting cash).
    if live:
        if st.live_start_equity is None and equity > 0:
            st.live_start_equity = equity
            db.commit()
        baseline = st.live_start_equity or equity
    else:
        baseline = st.initial_cash
    ret_pct = (float(equity) / float(baseline) - 1.0) * 100.0 if baseline else 0.0
    status = BotStatusOut(
        enabled=st.enabled, tick_seconds=st.tick_seconds, mode=st.mode, dry_run=st.dry_run,
        max_order_usd=st.max_order_usd, daily_cap_usd=st.daily_cap_usd, daily_spent_usd=st.daily_spent_usd,
        luno_configured=luno_ok, initial_cash=baseline, cash=st.cash,
        realized_pnl=realized, equity=equity, return_pct=ret_pct,
        open_positions=len(positions), started_at=st.started_at, last_tick_at=st.last_tick_at,
    )

    events = [
        BotEventOut(created_at=e.created_at, kind=e.kind, ticker=e.ticker, detail=e.detail, equity=e.equity)
        for e in db.scalars(select(BotEvent).order_by(BotEvent.created_at.desc()).limit(80)).all()
    ]
    rows = list(db.scalars(select(BotEquity).order_by(BotEquity.ts)).all())
    if len(rows) > 400:
        rows = rows[::len(rows) // 400 + 1]
    curve = [BotEquityPoint(ts=r.ts, equity=r.equity) for r in rows]

    note = _NOTE_PAPER if st.mode == "paper" else (_NOTE_LIVE_DRY if st.dry_run else _NOTE_LIVE_REAL)
    return BotResponse(status=status, positions=positions, events=events, equity_curve=curve, note=note)


@router.get("", response_model=BotResponse)
def get_bot(db: Session = Depends(get_db)) -> BotResponse:
    return _build_response(db)


@router.post("/start", response_model=BotResponse)
def start_bot(db: Session = Depends(get_db)) -> BotResponse:
    engine.start(db)
    return _build_response(db)


@router.post("/stop", response_model=BotResponse)
def stop_bot(db: Session = Depends(get_db)) -> BotResponse:
    engine.stop(db)
    return _build_response(db)


@router.post("/reset", response_model=BotResponse)
def reset_bot(db: Session = Depends(get_db)) -> BotResponse:
    engine.reset(db)
    return _build_response(db)


@router.post("/mode", response_model=BotResponse)
def set_mode(payload: ModeUpdate, db: Session = Depends(get_db)) -> BotResponse:
    try:
        engine.set_mode(db, payload.mode)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _build_response(db)


@router.post("/dry-run", response_model=BotResponse)
def set_dry_run(payload: DryRunUpdate, db: Session = Depends(get_db)) -> BotResponse:
    engine.set_dry_run(db, payload.dry_run)
    return _build_response(db)


@router.post("/caps", response_model=BotResponse)
def set_caps(payload: CapsUpdate, db: Session = Depends(get_db)) -> BotResponse:
    engine.set_caps(db, max_order_usd=payload.max_order_usd, daily_cap_usd=payload.daily_cap_usd)
    return _build_response(db)


@router.get("/luno", response_model=LunoStatusOut)
def luno_status() -> LunoStatusOut:
    """Read-only Luno connection + balances (no orders placed)."""
    return LunoStatusOut(**engine.luno_status())


@router.get("/performance", response_model=BotPerformanceOut)
def bot_performance(db: Session = Depends(get_db)) -> BotPerformanceOut:
    """Realised win-rate / P&L from the bot's own closed trades (paper vs live)."""
    s = bot_perf.all_stats(db)
    return BotPerformanceOut(paper=VenueStats(**s["paper"]), luno=VenueStats(**s["luno"]))
