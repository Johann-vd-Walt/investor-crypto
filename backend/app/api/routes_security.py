"""Security / access-log endpoints. Gated by the auth middleware (owner only)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.repositories import auth_events as auth_events_repo
from app.schemas.security import AccessLogResponse, AuthEventOut, AuthSummary

router = APIRouter(prefix="/api/security", tags=["security"])


@router.get("/access-log", response_model=AccessLogResponse)
def access_log(
    limit: int = Query(200, ge=1, le=1000),
    db: Session = Depends(get_db),
) -> AccessLogResponse:
    """Recent attempts to log in to the app, newest first, plus a 24h summary."""
    events = auth_events_repo.list_recent(db, limit=limit)
    summary = auth_events_repo.summary(db, hours=24)
    return AccessLogResponse(
        summary=AuthSummary(**summary),
        events=[AuthEventOut.model_validate(e) for e in events],
    )
