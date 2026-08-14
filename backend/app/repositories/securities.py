"""Data-access functions for ``securities`` (Guardrail 2.4).

All queries live here; the API layer never issues raw SQL.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Security


def get_by_id(db: Session, security_id: int) -> Security | None:
    return db.get(Security, security_id)


def get_by_ticker(db: Session, ticker: str) -> Security | None:
    stmt = select(Security).where(Security.ticker == ticker.upper())
    return db.scalar(stmt)


def list_missing_sector(db: Session) -> list[Security]:
    """Securities with no sector set yet."""
    stmt = select(Security).where(Security.sector.is_(None)).order_by(Security.ticker)
    return list(db.scalars(stmt).all())


def set_sector(db: Session, *, security: Security, sector: str) -> None:
    security.sector = sector
    db.flush()


def list_securities(
    db: Session,
    *,
    query: str | None = None,
    sector: str | None = None,
    active: bool | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[Security], int]:
    """Return ``(items, total)`` for a filtered, paginated listing."""
    stmt = select(Security)
    if query:
        like = f"%{query}%"
        stmt = stmt.where(
            (Security.ticker.like(like)) | (Security.name.like(like))
        )
    if sector:
        stmt = stmt.where(Security.sector == sector)
    if active is not None:
        stmt = stmt.where(Security.is_active.is_(active))

    # Count via a subquery (avoids loading rows just to count).
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = db.scalar(count_stmt) or 0

    stmt = stmt.order_by(Security.ticker).limit(limit).offset(offset)
    items = list(db.scalars(stmt).all())
    return items, total


def upsert(
    db: Session,
    *,
    ticker: str,
    name: str,
    isin: str | None = None,
    sector: str | None = None,
    currency: str = "ZAR",
    is_active: bool = True,
) -> tuple[Security, bool]:
    """Insert or update a security by ticker. Returns ``(security, created)``.

    Used by the seed job so re-running it is idempotent.
    """
    existing = get_by_ticker(db, ticker)
    if existing is None:
        sec = Security(
            ticker=ticker.upper(),
            name=name,
            isin=isin,
            sector=sector,
            currency=currency,
            is_active=is_active,
        )
        db.add(sec)
        db.flush()
        return sec, True

    existing.name = name
    if isin is not None:
        existing.isin = isin
    if sector is not None:
        existing.sector = sector
    existing.currency = currency
    existing.is_active = is_active
    db.flush()
    return existing, False
