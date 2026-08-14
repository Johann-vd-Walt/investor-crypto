"""SENS announcement endpoints (Phase D).

GET /api/sens                recent announcements (all)
GET /api/sens?ticker=NPN     announcements mapped to a security
"""

from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.repositories import securities as securities_repo
from app.repositories import sens as sens_repo
from app.schemas.sens import SensListResponse, SensOut

router = APIRouter(prefix="/api/sens", tags=["sens"])


@router.get("", response_model=SensListResponse)
def list_sens(
    ticker: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> SensListResponse:
    cache: dict[int, str] = {}

    def ticker_for(sid: int | None) -> str | None:
        if sid is None:
            return None
        if sid not in cache:
            sec = securities_repo.get_by_id(db, sid)
            cache[sid] = sec.ticker if sec else str(sid)
        return cache[sid]

    if ticker:
        sec = securities_repo.get_by_ticker(db, ticker)
        if sec is None:
            raise HTTPException(status_code=404, detail=f"Unknown ticker: {ticker}")
        rows = sens_repo.list_for_security(db, security_id=sec.id, limit=limit)
        resolved = sec.ticker
    else:
        rows = sens_repo.list_recent(db, limit=limit)
        resolved = None

    def clean(text: str | None) -> str | None:
        return re.sub("<[^>]+>", "", text).strip() if text else None

    return SensListResponse(
        ticker=resolved,
        count=len(rows),
        items=[
            SensOut(
                id=r.id,
                security_id=r.security_id,
                ticker=ticker_for(r.security_id),
                source=r.source,
                url=r.url,
                headline=r.headline,
                summary=clean(r.summary),
                category=r.category,
                published_at=r.published_at,
            )
            for r in rows
        ],
    )
