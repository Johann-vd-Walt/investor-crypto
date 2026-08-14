"""Data-access for ``sens_announcements`` (Guardrail 2.4). Deduped by url hash."""

from __future__ import annotations

import hashlib
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import SensAnnouncement


def url_hash(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


def exists(db: Session, *, url: str) -> bool:
    return db.scalar(select(SensAnnouncement.id).where(SensAnnouncement.url_hash == url_hash(url))) is not None


def upsert(
    db: Session,
    *,
    source: str,
    url: str,
    headline: str,
    summary: str | None,
    category: str | None,
    published_at: datetime | None,
    security_id: int | None,
    raw: dict | None,
) -> tuple[SensAnnouncement, bool]:
    h = url_hash(url)
    existing = db.scalar(select(SensAnnouncement).where(SensAnnouncement.url_hash == h))
    if existing is not None:
        return existing, False
    row = SensAnnouncement(
        source=source,
        url=url[:768],
        url_hash=h,
        headline=headline[:512],
        summary=summary,
        category=category,
        published_at=published_at,
        security_id=security_id,
        raw=raw,
    )
    db.add(row)
    db.flush()
    return row, True


def list_for_security(
    db: Session, *, security_id: int, limit: int = 50
) -> list[SensAnnouncement]:
    stmt = (
        select(SensAnnouncement)
        .where(SensAnnouncement.security_id == security_id)
        .order_by(SensAnnouncement.published_at.desc())
        .limit(limit)
    )
    return list(db.scalars(stmt).all())


def list_recent(db: Session, *, limit: int = 50) -> list[SensAnnouncement]:
    stmt = (
        select(SensAnnouncement)
        .order_by(SensAnnouncement.published_at.desc())
        .limit(limit)
    )
    return list(db.scalars(stmt).all())
