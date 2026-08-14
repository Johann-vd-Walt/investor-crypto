"""Data-access for ``trades`` (real, manually-entered). Prices in cents."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Trade, TradeSide


def create(
    db: Session,
    *,
    security_id: int,
    side: TradeSide,
    quantity: int,
    price: Decimal,       # cents
    fees: Decimal,        # cents
    trade_datetime: datetime,
    linked_signal_id: int | None = None,
    rationale: str | None = None,
) -> Trade:
    trade = Trade(
        security_id=security_id,
        side=side,
        quantity=quantity,
        price=price,
        fees=fees,
        trade_datetime=trade_datetime,
        linked_signal_id=linked_signal_id,
        rationale=rationale,
    )
    db.add(trade)
    db.flush()
    return trade


def get(db: Session, trade_id: int) -> Trade | None:
    return db.get(Trade, trade_id)


def list_trades(db: Session, *, limit: int = 200, offset: int = 0) -> tuple[list[Trade], int]:
    from sqlalchemy import func

    total = db.scalar(select(func.count()).select_from(Trade)) or 0
    stmt = (
        select(Trade)
        .order_by(Trade.trade_datetime.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(db.scalars(stmt).all()), total


def list_all_through(db: Session, *, end: datetime) -> list[Trade]:
    """All trades up to ``end`` (needed for FIFO base-cost of tax-year sells)."""
    stmt = (
        select(Trade)
        .where(Trade.trade_datetime <= end)
        .order_by(Trade.trade_datetime)
    )
    return list(db.scalars(stmt).all())


def delete(db: Session, trade: Trade) -> None:
    db.delete(trade)
    db.flush()
