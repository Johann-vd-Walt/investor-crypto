"""Repository for the security login log (auth_events)."""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.db.models import AuthEvent

# Keep the log bounded — 90 days is plenty to spot probing without growing forever.
_RETENTION_DAYS = 90


def record(db: Session, *, event: str, ip: str | None, user_agent: str | None) -> None:
    """Best-effort insert of one login attempt. Never raises into the caller."""
    try:
        db.add(AuthEvent(event=event, ip=ip, user_agent=(user_agent or None)))
        db.commit()
    except Exception:  # noqa: BLE001 — logging a login must never break login
        db.rollback()


def list_recent(db: Session, *, limit: int = 200) -> list[AuthEvent]:
    stmt = select(AuthEvent).order_by(AuthEvent.created_at.desc()).limit(limit)
    return list(db.execute(stmt).scalars().all())


def summary(db: Session, *, hours: int = 24) -> dict:
    """Counts over the last ``hours`` window, plus the distinct offending IPs."""
    since = datetime.utcnow() - timedelta(hours=hours)
    rows = db.execute(
        select(AuthEvent.event, func.count())
        .where(AuthEvent.created_at >= since)
        .group_by(AuthEvent.event)
    ).all()
    counts = {event: int(n) for event, n in rows}
    distinct_fail_ips = db.execute(
        select(func.count(func.distinct(AuthEvent.ip))).where(
            AuthEvent.created_at >= since,
            AuthEvent.event.in_(("failed", "locked")),
        )
    ).scalar_one()
    return {
        "window_hours": hours,
        "success": counts.get("success", 0),
        "failed": counts.get("failed", 0),
        "locked": counts.get("locked", 0),
        "distinct_failed_ips": int(distinct_fail_ips or 0),
    }


def prune_old(db: Session) -> int:
    """Delete events older than the retention window. Returns rows removed."""
    cutoff = datetime.utcnow() - timedelta(days=_RETENTION_DAYS)
    result = db.execute(delete(AuthEvent).where(AuthEvent.created_at < cutoff))
    db.commit()
    return int(result.rowcount or 0)
