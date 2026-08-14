"""Data-access for ``provider_calls`` (Guardrail 2.6 — log every external call)."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.db.models import ProviderCall
from app.providers.base import ProviderCallInfo


def record(db: Session, info: ProviderCallInfo) -> None:
    """Persist one provider call. Flushes but does not commit."""
    db.add(
        ProviderCall(
            provider=info.provider,
            endpoint=info.endpoint,
            status_code=info.status_code,
            rows_returned=info.rows_returned,
            note=info.note,
        )
    )
    db.flush()
