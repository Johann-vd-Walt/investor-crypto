"""Data-access for the ``derivative_metrics`` time series (Tier 1)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.orm import Session

from app.db.models import DerivativeMetric


def upsert_metrics(
    db: Session,
    *,
    security_id: int,
    metric: str,
    points: list[tuple[datetime, Decimal]],
) -> int:
    """Idempotently store (ts, value) points for one (security, metric)."""
    if not points:
        return 0
    payload = [
        {"security_id": security_id, "metric": metric, "ts": ts, "value": val}
        for ts, val in points
    ]
    stmt = mysql_insert(DerivativeMetric).values(payload)
    stmt = stmt.on_duplicate_key_update(value=stmt.inserted.value)
    db.execute(stmt)
    return len(payload)


def get_series(
    db: Session, *, security_id: int, metric: str, limit: int | None = None
) -> list[DerivativeMetric]:
    """Ascending-by-time points for one (security, metric)."""
    stmt = (
        select(DerivativeMetric)
        .where(
            DerivativeMetric.security_id == security_id,
            DerivativeMetric.metric == metric,
        )
        .order_by(DerivativeMetric.ts)
    )
    rows = list(db.scalars(stmt).all())
    if limit is not None and len(rows) > limit:
        rows = rows[-limit:]
    return rows


def latest(db: Session, *, security_id: int, metric: str) -> DerivativeMetric | None:
    stmt = (
        select(DerivativeMetric)
        .where(
            DerivativeMetric.security_id == security_id,
            DerivativeMetric.metric == metric,
        )
        .order_by(DerivativeMetric.ts.desc())
        .limit(1)
    )
    return db.scalars(stmt).first()


def security_ids_with_metrics(db: Session) -> list[int]:
    stmt = select(DerivativeMetric.security_id).distinct()
    return list(db.scalars(stmt).all())
