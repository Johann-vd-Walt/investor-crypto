"""Data-access for ``macro_series`` (Guardrail 2.4).

Macro values are stored in their native units (USD, ZAR/USD, index points,
index level) — the ZAc-cents convention applies only to JSE share prices.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.orm import Session

from app.db.models import MacroSeries
from app.providers.base import Observation


def upsert_observations(
    db: Session,
    *,
    series_code: str,
    source: str,
    observations: list[Observation],
) -> int:
    """Idempotently insert/update observations. Returns rows written."""
    if not observations:
        return 0
    rows = [
        {
            "series_code": series_code,
            "observation_date": o.observation_date,
            "value": o.value,
            "unit": o.unit,
            "source": source,
        }
        for o in observations
    ]
    stmt = mysql_insert(MacroSeries).values(rows)
    stmt = stmt.on_duplicate_key_update(
        value=stmt.inserted.value,
        unit=stmt.inserted.unit,
        source=stmt.inserted.source,
    )
    db.execute(stmt)
    return len(rows)


def get_series(
    db: Session,
    *,
    series_code: str,
    start: date | None = None,
    end: date | None = None,
) -> list[MacroSeries]:
    stmt = select(MacroSeries).where(MacroSeries.series_code == series_code)
    if start:
        stmt = stmt.where(MacroSeries.observation_date >= start)
    if end:
        stmt = stmt.where(MacroSeries.observation_date <= end)
    return list(db.scalars(stmt.order_by(MacroSeries.observation_date)).all())


def get_latest(db: Session, *, series_code: str) -> MacroSeries | None:
    stmt = (
        select(MacroSeries)
        .where(MacroSeries.series_code == series_code)
        .order_by(MacroSeries.observation_date.desc())
        .limit(1)
    )
    return db.scalar(stmt)
