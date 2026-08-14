"""Watchlist CRUD endpoints (Section 11)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.repositories import securities as securities_repo
from app.repositories import watchlist as watchlist_repo
from app.schemas.watchlist import WatchlistCreate, WatchlistItemOut

router = APIRouter(prefix="/api/watchlist", tags=["watchlist"])


@router.get("", response_model=list[WatchlistItemOut])
def list_watchlist(db: Session = Depends(get_db)) -> list[WatchlistItemOut]:
    entries = watchlist_repo.list_entries(db)
    return [WatchlistItemOut.model_validate(e) for e in entries]


@router.post("", response_model=WatchlistItemOut, status_code=status.HTTP_201_CREATED)
def add_to_watchlist(
    payload: WatchlistCreate, db: Session = Depends(get_db)
) -> WatchlistItemOut:
    sec = securities_repo.get_by_ticker(db, payload.ticker)
    if sec is None:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown ticker: {payload.ticker}. Add the security first.",
        )

    if watchlist_repo.get_by_security_id(db, sec.id) is not None:
        raise HTTPException(
            status_code=409,
            detail=f"{sec.ticker} is already on the watchlist.",
        )

    entry = watchlist_repo.add(db, security_id=sec.id, notes=payload.notes)
    db.commit()
    return WatchlistItemOut.model_validate(entry)


@router.delete("/{watchlist_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_from_watchlist(watchlist_id: int, db: Session = Depends(get_db)) -> None:
    entry = watchlist_repo.get_by_id(db, watchlist_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Watchlist entry not found.")
    watchlist_repo.remove(db, entry)
    db.commit()
