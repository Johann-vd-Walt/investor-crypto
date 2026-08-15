"""Derivatives / positioning endpoints (Tier 1). Free Binance futures data."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.repositories import derivatives as deriv_repo
from app.repositories import securities as securities_repo
from app.schemas.positioning import PositioningListResponse, PositioningSnapshot
from app.services import positioning as positioning_service

router = APIRouter(prefix="/api/positioning", tags=["positioning"])


@router.get("", response_model=PositioningListResponse)
def list_positioning(db: Session = Depends(get_db)) -> PositioningListResponse:
    """Positioning snapshots for every asset that has any futures data yet."""
    ids = set(deriv_repo.security_ids_with_metrics(db))
    items = []
    for sec_id in ids:
        sec = securities_repo.get_by_id(db, sec_id)
        if sec is not None:
            items.append(positioning_service.build_snapshot(db, sec))
    # Deterministic order: assets with signals first, then by ticker.
    items.sort(key=lambda s: (not s.available, s.ticker))
    return PositioningListResponse(count=len(items), items=items)


@router.get("/{ticker}", response_model=PositioningSnapshot)
def get_positioning(ticker: str, db: Session = Depends(get_db)) -> PositioningSnapshot:
    sec = securities_repo.get_by_ticker(db, ticker)
    if sec is None:
        raise HTTPException(status_code=404, detail=f"Unknown ticker: {ticker}")
    return positioning_service.build_snapshot(db, sec)
