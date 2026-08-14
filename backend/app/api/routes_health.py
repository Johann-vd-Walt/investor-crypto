"""Health endpoint: reports app + database + provider status.

Returns HTTP 200 with status "degraded" when the DB is unreachable, so the
frontend data-freshness banner can render rather than seeing a hard 5xx.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.config import get_settings
from app.db.session import check_db_connection
from app.schemas.health import DatabaseHealth, HealthResponse

router = APIRouter(tags=["health"])


@router.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    settings = get_settings()
    connected, error = check_db_connection()
    return HealthResponse(
        status="ok" if connected else "degraded",
        app_env=settings.app_env,
        database=DatabaseHealth(connected=connected, error=error),
        providers=settings.enabled_providers,
    )
