"""Real-time PAPER trading bot endpoints. Simulated only — no real orders."""

from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.bot import engine
from app.config import get_settings
from app.db.models import BotEquity, BotEvent, BotPosition, Security
from app.db.session import get_db
from app.schemas.bot import (
    BotEquityPoint, BotEventOut, BotPositionOut, BotResponse, BotStatusOut,
)

router = APIRouter(prefix="/api/bot", tags=["bot"])

_NOTE = (
    "PAPER bot: simulated fills against live prices — no real orders, no exchange "
    "keys, no real money. The backtests show no established edge (Deflated Sharpe "
    "~22%) and buy-and-hold beat the strategy, so treat a rising curve with "
    "scepticism and a falling one as the expected result."
)


def _build_response(db: Session) -> BotResponse:
    st = engine.ensure_state(db)

    open_pos = list(db.scalars(select(BotPosition).where(BotPosition.status == "OPEN")).all())
    sec_by_id = {
        s.id: s for s in db.scalars(
            select(Security).where(Security.id.in_([p.security_id for p in open_pos]))
        ).all()
    } if open_pos else {}
    tickers = [sec_by_id[p.security_id].ticker for p in open_pos if p.security_id in sec_by_id]
    prices = engine.fetch_live_prices(tickers, get_settings().binance_base_url)

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
            live_price=live, cost_basis=p.cost_basis, market_value=mv,
            unrealized_pnl=upnl, unrealized_pct=upct,
        ))

    ret_pct = (float(equity) / float(st.initial_cash) - 1.0) * 100.0 if st.initial_cash else 0.0
    status = BotStatusOut(
        enabled=st.enabled, tick_seconds=st.tick_seconds, initial_cash=st.initial_cash,
        cash=st.cash, realized_pnl=st.realized_pnl, equity=equity, return_pct=ret_pct,
        open_positions=len(positions), started_at=st.started_at, last_tick_at=st.last_tick_at,
    )

    events = [
        BotEventOut(created_at=e.created_at, kind=e.kind, ticker=e.ticker, detail=e.detail, equity=e.equity)
        for e in db.scalars(select(BotEvent).order_by(BotEvent.created_at.desc()).limit(80)).all()
    ]

    rows = list(db.scalars(select(BotEquity).order_by(BotEquity.ts)).all())
    if len(rows) > 400:  # downsample to keep the payload light
        stride = len(rows) // 400 + 1
        rows = rows[::stride]
    curve = [BotEquityPoint(ts=r.ts, equity=r.equity) for r in rows]

    return BotResponse(status=status, positions=positions, events=events, equity_curve=curve, note=_NOTE)


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
