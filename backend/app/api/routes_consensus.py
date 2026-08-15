"""Copy-trading crowd-consensus endpoint (Tier 4). Free OKX public data."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.consensus import ConsensusResponse
from app.services import consensus as consensus_service

router = APIRouter(prefix="/api/consensus", tags=["consensus"])


@router.get("", response_model=ConsensusResponse)
def get_consensus(db: Session = Depends(get_db)) -> ConsensusResponse:
    """What OKX's top lead traders are net long/short, by coin. Cached ~15 min.

    Low-confidence context only — see the response `caveat`.
    """
    return consensus_service.build_consensus(db)
