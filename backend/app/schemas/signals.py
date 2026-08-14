"""Signal response/request schemas (§11).

Scores are in -1..1. Suggested entry/stop are stored in cents but returned in
RAND (presentation boundary, Guardrail 2.3). The full ``rationale`` is always
included so the reasoning is never hidden (§8).
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from app.db.models import SignalDirection, SignalStatus
from app.schemas.common import DecimalAsFloat


class SignalOut(BaseModel):
    id: int
    security_id: int
    ticker: str
    generated_at: datetime
    horizon_days: int
    direction: SignalDirection
    score: DecimalAsFloat
    confidence: DecimalAsFloat | None
    technical_score: DecimalAsFloat | None
    macro_score: DecimalAsFloat | None
    sentiment_score: DecimalAsFloat | None
    suggested_entry: DecimalAsFloat | None  # Rand
    suggested_stop: DecimalAsFloat | None   # Rand
    suggested_size: int | None
    rationale: dict | None
    status: SignalStatus


class SignalListResponse(BaseModel):
    items: list[SignalOut]
    total: int
    limit: int
    offset: int


class SignalStatusUpdate(BaseModel):
    status: SignalStatus
