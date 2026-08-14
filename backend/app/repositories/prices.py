"""Data-access for ``price_bars`` (Guardrail 2.4). Prices stored in cents."""

from __future__ import annotations

from datetime import date, datetime, time

from sqlalchemy import select
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.orm import Session

from app.db.models import PriceBar
from app.providers.base import Bar


def upsert_bars(
    db: Session,
    *,
    security_id: int,
    timeframe: str,
    source: str,
    bars: list[Bar],
) -> int:
    """Idempotently insert/update bars. Returns the number of rows written.

    Uses MySQL ``INSERT ... ON DUPLICATE KEY UPDATE`` so re-ingesting a day is
    safe (dedupe on the composite PK).
    """
    if not bars:
        return 0

    rows = [
        {
            "security_id": security_id,
            "timeframe": timeframe,
            "bar_datetime": b.bar_datetime,
            "open": b.open,
            "high": b.high,
            "low": b.low,
            "close": b.close,
            "adj_close": b.adj_close,
            "volume": b.volume,
            "source": source,
            "is_delayed": b.is_delayed,
        }
        for b in bars
    ]

    stmt = mysql_insert(PriceBar).values(rows)
    stmt = stmt.on_duplicate_key_update(
        open=stmt.inserted.open,
        high=stmt.inserted.high,
        low=stmt.inserted.low,
        close=stmt.inserted.close,
        adj_close=stmt.inserted.adj_close,
        volume=stmt.inserted.volume,
        source=stmt.inserted.source,
        is_delayed=stmt.inserted.is_delayed,
    )
    db.execute(stmt)
    return len(rows)


def get_bars(
    db: Session,
    *,
    security_id: int,
    timeframe: str = "1d",
    start: date | None = None,
    end: date | None = None,
) -> list[PriceBar]:
    stmt = select(PriceBar).where(
        PriceBar.security_id == security_id,
        PriceBar.timeframe == timeframe,
    )
    if start:
        stmt = stmt.where(PriceBar.bar_datetime >= datetime.combine(start, time.min))
    if end:
        stmt = stmt.where(PriceBar.bar_datetime <= datetime.combine(end, time.max))
    stmt = stmt.order_by(PriceBar.bar_datetime)
    return list(db.scalars(stmt).all())


def security_ids_with_bars(db: Session, *, timeframe: str = "1d") -> list[int]:
    stmt = (
        select(PriceBar.security_id)
        .where(PriceBar.timeframe == timeframe)
        .distinct()
    )
    return list(db.scalars(stmt).all())


def get_latest_bar(
    db: Session, *, security_id: int, timeframe: str = "1d"
) -> PriceBar | None:
    stmt = (
        select(PriceBar)
        .where(PriceBar.security_id == security_id, PriceBar.timeframe == timeframe)
        .order_by(PriceBar.bar_datetime.desc())
        .limit(1)
    )
    return db.scalar(stmt)
