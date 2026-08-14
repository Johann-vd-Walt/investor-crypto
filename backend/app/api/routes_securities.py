"""Securities read endpoints (Section 11)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.repositories import securities as securities_repo
from app.schemas.securities import SecurityListResponse, SecurityOut

router = APIRouter(prefix="/api/securities", tags=["securities"])


@router.get("", response_model=SecurityListResponse)
def list_securities(
    query: str | None = Query(default=None, description="Match ticker or name"),
    sector: str | None = Query(default=None),
    active: bool | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> SecurityListResponse:
    items, total = securities_repo.list_securities(
        db,
        query=query,
        sector=sector,
        active=active,
        limit=limit,
        offset=offset,
    )
    return SecurityListResponse(
        items=[SecurityOut.model_validate(s) for s in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{ticker}", response_model=SecurityOut)
def get_security(ticker: str, db: Session = Depends(get_db)) -> SecurityOut:
    sec = securities_repo.get_by_ticker(db, ticker)
    if sec is None:
        raise HTTPException(status_code=404, detail=f"Unknown ticker: {ticker}")
    return SecurityOut.model_validate(sec)
