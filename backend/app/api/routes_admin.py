"""Dev-only admin endpoints (Section 9).

``POST /api/admin/run-job`` lets you fire an ingestion job on demand during
development. Disabled outside development to avoid accidental production runs.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from app import auth
from app.config import get_settings
from app.ingestion.jobs import JOBS
from app.schemas.admin import RunJobRequest, RunJobResponse

logger = logging.getLogger("app.admin")

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.post("/run-job", response_model=RunJobResponse)
def run_job(payload: RunJobRequest) -> RunJobResponse:
    settings = get_settings()
    # Allowed in development, or in production when the TOTP gate is on (so the
    # "Refresh" buttons work but only for an authenticated owner). Blocked if
    # production AND auth disabled — don't expose job triggers unauthenticated.
    if settings.app_env != "development" and not auth.is_enabled(settings):
        raise HTTPException(
            status_code=403,
            detail="run-job requires development mode or an enabled TOTP login.",
        )

    job = JOBS.get(payload.job_name)
    if job is None:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown job '{payload.job_name}'. Known: {sorted(JOBS)}",
        )

    logger.info("Manual run-job: %s params=%s", payload.job_name, payload.params)
    result = job(**payload.params)
    return RunJobResponse(job_name=payload.job_name, result=result)
