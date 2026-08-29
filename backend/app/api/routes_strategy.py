"""Strategy auditor endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.strategy import AuditMetrics, AuditResponse, Finding
from app.services import strategy_audit

router = APIRouter(prefix="/api/strategy", tags=["strategy"])


@router.get("/audit", response_model=AuditResponse)
def audit(db: Session = Depends(get_db)) -> AuditResponse:
    """Review the current strategy (settings + fresh backtest + track record) and
    return honest findings. Runs a momentum backtest, so it takes a few seconds."""
    r = strategy_audit.audit(db)
    return AuditResponse(
        findings=[Finding(**f) for f in r["findings"]],
        metrics=AuditMetrics(**r["metrics"]) if r["metrics"] else None,
    )
