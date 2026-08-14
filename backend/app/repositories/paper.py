"""Data-access for ``paper_trades`` (Guardrail 2.4). Prices in cents."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import PaperTrade, PaperTradeStatus


def has_open_for_security(db: Session, *, security_id: int) -> bool:
    stmt = select(PaperTrade.id).where(
        PaperTrade.security_id == security_id,
        PaperTrade.status == PaperTradeStatus.OPEN,
    )
    return db.scalar(stmt) is not None


def open_trade(
    db: Session,
    *,
    signal_id: int | None,
    security_id: int,
    entry_datetime: datetime,
    entry_price: Decimal,
    quantity: int,
    stop_price: Decimal | None,
) -> PaperTrade:
    trade = PaperTrade(
        signal_id=signal_id,
        security_id=security_id,
        entry_datetime=entry_datetime,
        entry_price=entry_price,
        quantity=quantity,
        stop_price=stop_price,
        status=PaperTradeStatus.OPEN,
    )
    db.add(trade)
    db.flush()
    return trade


def list_open(db: Session) -> list[PaperTrade]:
    return list(
        db.scalars(select(PaperTrade).where(PaperTrade.status == PaperTradeStatus.OPEN)).all()
    )


def list_closed(db: Session) -> list[PaperTrade]:
    stmt = (
        select(PaperTrade)
        .where(PaperTrade.status == PaperTradeStatus.CLOSED)
        .order_by(PaperTrade.exit_datetime)
    )
    return list(db.scalars(stmt).all())


def list_all(db: Session, *, limit: int = 200) -> list[PaperTrade]:
    stmt = select(PaperTrade).order_by(PaperTrade.entry_datetime.desc()).limit(limit)
    return list(db.scalars(stmt).all())


def close_trade(
    db: Session,
    *,
    trade: PaperTrade,
    exit_datetime: datetime,
    exit_price: Decimal,
    pnl: Decimal,
) -> PaperTrade:
    trade.exit_datetime = exit_datetime
    trade.exit_price = exit_price
    trade.pnl = pnl
    trade.status = PaperTradeStatus.CLOSED
    db.flush()
    return trade
