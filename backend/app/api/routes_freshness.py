"""Data-freshness endpoint (§9, §12).

Reports, per data family, when we last ingested and how recent the data is, plus
a staleness flag so the UI can warn everywhere data appears. Thresholds are
lenient (data is delayed/EOD and markets close on weekends) — "stale" means the
ingestion pipeline hasn't run recently, not that a single feed is momentarily
behind.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.repositories import freshness as freshness_repo

router = APIRouter(prefix="/api/freshness", tags=["freshness"])

# Max age of the last ingest before a family is considered stale (hours).
_STALE_HOURS = {"prices": 120, "macro": 48, "news": 12, "signals": 96}


class FamilyOut(BaseModel):
    name: str
    last_ingest: datetime | None
    latest_data: datetime | None
    count: int
    stale: bool


class FreshnessResponse(BaseModel):
    as_of: datetime
    families: list[FamilyOut]
    overall_stale: bool


def _is_stale(name: str, last_ingest: datetime | None, now: datetime) -> bool:
    if last_ingest is None:
        return True  # nothing ingested yet
    # DB timestamps are naive (server local); compare naively against now.
    threshold = timedelta(hours=_STALE_HOURS.get(name, 48))
    return (now - last_ingest) > threshold


@router.get("", response_model=FreshnessResponse)
def freshness(db: Session = Depends(get_db)) -> FreshnessResponse:
    now = datetime.now()
    families = freshness_repo.get_freshness(db)
    out: list[FamilyOut] = []
    overall = False
    for f in families:
        stale = _is_stale(f.name, f.last_ingest, now)
        # An empty family isn't "stale" in an alarming way if never populated;
        # still flag it so the UI can prompt an initial ingest.
        overall = overall or (stale and f.count > 0)
        out.append(
            FamilyOut(
                name=f.name,
                last_ingest=f.last_ingest,
                latest_data=f.latest_data,
                count=f.count,
                stale=stale,
            )
        )
    return FreshnessResponse(as_of=now, families=out, overall_stale=overall)
