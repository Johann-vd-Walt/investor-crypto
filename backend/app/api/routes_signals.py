"""Signals endpoints (Section 11)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.models import Signal, SignalDirection
from app.db.session import get_db
from app.repositories import securities as securities_repo
from app.repositories import signals as signals_repo
from app.schemas.prices import cents_to_rand
from app.schemas.signals import SignalListResponse, SignalOut, SignalStatusUpdate

router = APIRouter(prefix="/api/signals", tags=["signals"])


def _to_out(db: Session, sig: Signal, ticker_cache: dict[int, str]) -> SignalOut:
    ticker = ticker_cache.get(sig.security_id)
    if ticker is None:
        sec = securities_repo.get_by_id(db, sig.security_id)
        ticker = sec.ticker if sec else str(sig.security_id)
        ticker_cache[sig.security_id] = ticker
    return SignalOut(
        id=sig.id,
        security_id=sig.security_id,
        ticker=ticker,
        generated_at=sig.generated_at,
        horizon_days=sig.horizon_days,
        direction=sig.direction,
        score=sig.score,
        confidence=sig.confidence,
        technical_score=sig.technical_score,
        macro_score=sig.macro_score,
        sentiment_score=sig.sentiment_score,
        suggested_entry=cents_to_rand(sig.suggested_entry),
        suggested_stop=cents_to_rand(sig.suggested_stop),
        suggested_size=sig.suggested_size,
        rationale=sig.rationale,
        status=sig.status,
    )


@router.get("", response_model=SignalListResponse)
def list_signals(
    on_date: date | None = Query(default=None, alias="date"),
    direction: SignalDirection | None = Query(default=None),
    min_score: float | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> SignalListResponse:
    items, total = signals_repo.list_signals(
        db,
        on_date=on_date,
        direction=direction,
        min_score=Decimal(str(min_score)) if min_score is not None else None,
        limit=limit,
        offset=offset,
    )
    cache: dict[int, str] = {}
    return SignalListResponse(
        items=[_to_out(db, s, cache) for s in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{signal_id}", response_model=SignalOut)
def get_signal(signal_id: int, db: Session = Depends(get_db)) -> SignalOut:
    sig = signals_repo.get(db, signal_id)
    if sig is None:
        raise HTTPException(status_code=404, detail="Signal not found.")
    return _to_out(db, sig, {})


@router.post("/{signal_id}/status", response_model=SignalOut)
def set_signal_status(
    signal_id: int, payload: SignalStatusUpdate, db: Session = Depends(get_db)
) -> SignalOut:
    sig = signals_repo.get(db, signal_id)
    if sig is None:
        raise HTTPException(status_code=404, detail="Signal not found.")
    signals_repo.update_status(db, signal=sig, status=payload.status)
    db.commit()
    return _to_out(db, sig, {})
