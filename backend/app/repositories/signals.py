"""Data-access for ``signals`` (Guardrail 2.4)."""

from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.db.models import Signal, SignalDirection, SignalStatus


def supersede_open(db: Session, *, security_id: int) -> int:
    """Expire any still-OPEN signals for a security before a fresh one is written.

    Keeps at most one OPEN signal per coin (the latest), so the Signals page and
    the bot see one current read instead of a pile of duplicates. ACTED/DISMISSED
    signals are left untouched (history preserved).
    """
    result = db.execute(
        update(Signal)
        .where(Signal.security_id == security_id, Signal.status == SignalStatus.OPEN)
        .values(status=SignalStatus.EXPIRED)
    )
    return int(result.rowcount or 0)


def create(db: Session, draft) -> Signal:
    """Persist a SignalDraft (see signals.engine.SignalDraft)."""
    sig = Signal(
        security_id=draft.security_id,
        generated_at=draft.generated_at,
        horizon_days=draft.horizon_days,
        direction=draft.direction,
        score=draft.score,
        confidence=draft.confidence,
        technical_score=draft.technical_score,
        macro_score=draft.macro_score,
        sentiment_score=draft.sentiment_score,
        suggested_entry=draft.suggested_entry,
        suggested_stop=draft.suggested_stop,
        suggested_size=draft.suggested_size,
        rationale=draft.rationale,
        status=SignalStatus.OPEN,
    )
    db.add(sig)
    db.flush()
    return sig


def get(db: Session, signal_id: int) -> Signal | None:
    return db.get(Signal, signal_id)


def list_signals(
    db: Session,
    *,
    on_date: date | None = None,
    direction: SignalDirection | None = None,
    min_score: Decimal | None = None,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[Signal], int]:
    stmt = select(Signal)
    if on_date:
        stmt = stmt.where(
            Signal.generated_at >= datetime.combine(on_date, time.min),
            Signal.generated_at <= datetime.combine(on_date, time.max),
        )
    if direction is not None:
        stmt = stmt.where(Signal.direction == direction)
    if min_score is not None:
        stmt = stmt.where(Signal.score >= min_score)

    from sqlalchemy import func

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    # Rank by absolute conviction, newest first.
    stmt = stmt.order_by(Signal.generated_at.desc(), Signal.score.desc()).limit(limit).offset(offset)
    return list(db.scalars(stmt).all()), total


def latest_for_security(db: Session, *, security_id: int) -> Signal | None:
    stmt = (
        select(Signal)
        .where(Signal.security_id == security_id)
        .order_by(Signal.generated_at.desc())
        .limit(1)
    )
    return db.scalar(stmt)


def update_status(db: Session, *, signal: Signal, status: SignalStatus) -> Signal:
    signal.status = status
    db.flush()
    return signal
