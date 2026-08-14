"""Data-access for the ``indicator_values`` cache (Guardrail 2.4)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.orm import Session

from app.db.models import IndicatorValue


def get_values(
    db: Session,
    *,
    security_id: int,
    timeframe: str = "1d",
    names: list[str] | None = None,
) -> list[IndicatorValue]:
    stmt = select(IndicatorValue).where(
        IndicatorValue.security_id == security_id,
        IndicatorValue.timeframe == timeframe,
    )
    if names:
        stmt = stmt.where(IndicatorValue.indicator.in_(names))
    stmt = stmt.order_by(IndicatorValue.indicator, IndicatorValue.bar_datetime)
    return list(db.scalars(stmt).all())


def upsert_values(
    db: Session,
    *,
    security_id: int,
    timeframe: str,
    rows: list[dict],
) -> int:
    """Idempotently cache indicator values.

    ``rows`` items: {bar_datetime, indicator, value|None}. Returns rows written.
    """
    if not rows:
        return 0
    payload = [
        {
            "security_id": security_id,
            "timeframe": timeframe,
            "bar_datetime": r["bar_datetime"],
            "indicator": r["indicator"],
            "value": r["value"],
        }
        for r in rows
    ]
    stmt = mysql_insert(IndicatorValue).values(payload)
    stmt = stmt.on_duplicate_key_update(value=stmt.inserted.value)
    db.execute(stmt)
    return len(payload)
