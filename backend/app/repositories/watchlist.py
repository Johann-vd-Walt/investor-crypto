"""Data-access functions for ``watchlist`` (Guardrail 2.4)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.db.models import Watchlist


def list_entries(db: Session) -> list[Watchlist]:
    """All watchlist entries, each with its security eagerly loaded."""
    stmt = (
        select(Watchlist)
        .options(joinedload(Watchlist.security))
        .order_by(Watchlist.added_at.desc())
    )
    return list(db.scalars(stmt).all())


def get_by_id(db: Session, watchlist_id: int) -> Watchlist | None:
    return db.get(Watchlist, watchlist_id)


def get_by_security_id(db: Session, security_id: int) -> Watchlist | None:
    stmt = select(Watchlist).where(Watchlist.security_id == security_id)
    return db.scalar(stmt)


def add(db: Session, *, security_id: int, notes: str | None = None) -> Watchlist:
    entry = Watchlist(security_id=security_id, notes=notes)
    db.add(entry)
    db.flush()
    db.refresh(entry, attribute_names=["security"])
    return entry


def remove(db: Session, entry: Watchlist) -> None:
    db.delete(entry)
    db.flush()
