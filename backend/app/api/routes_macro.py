"""Macro endpoints (Section 11).

GET /api/macro            dashboard snapshot: latest value per known series
GET /api/macro/{code}     one series over a date range
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.providers.registry import (
    MACRO_SERIES_LABELS,
    MACRO_SERIES_PLAN,
    MACRO_SERIES_UNAVAILABLE,
)
from app.repositories import macro as macro_repo
from app.schemas.macro import (
    MacroObservationOut,
    MacroSeriesResponse,
    MacroSnapshotItem,
    MacroSnapshotResponse,
)

router = APIRouter(prefix="/api/macro", tags=["macro"])

# Ordered list of series the snapshot reports (sourced + known-unavailable).
_PLAN_CODES = [code for code, _p, _k in MACRO_SERIES_PLAN]


@router.get("", response_model=MacroSnapshotResponse)
def macro_snapshot(db: Session = Depends(get_db)) -> MacroSnapshotResponse:
    items: list[MacroSnapshotItem] = []

    for code in _PLAN_CODES:
        latest = macro_repo.get_latest(db, series_code=code)
        label = MACRO_SERIES_LABELS.get(code, code)
        if latest is None:
            items.append(
                MacroSnapshotItem(
                    series_code=code, label=label, available=False,
                    note="No data ingested yet — run ingest_macro.",
                )
            )
        else:
            items.append(
                MacroSnapshotItem(
                    series_code=code, label=label, available=True,
                    value=latest.value, unit=latest.unit,
                    as_of=latest.observation_date, source=latest.source,
                )
            )

    # Series we knowingly cannot source freely yet (honest surfacing).
    for code, why in MACRO_SERIES_UNAVAILABLE.items():
        items.append(
            MacroSnapshotItem(
                series_code=code, label=MACRO_SERIES_LABELS.get(code, code),
                available=False, note=why,
            )
        )

    return MacroSnapshotResponse(items=items)


@router.get("/{series_code}", response_model=MacroSeriesResponse)
def macro_series(
    series_code: str,
    from_: date | None = Query(default=None, alias="from"),
    to: date | None = Query(default=None),
    db: Session = Depends(get_db),
) -> MacroSeriesResponse:
    code = series_code.upper()
    rows = macro_repo.get_series(db, series_code=code, start=from_, end=to)
    if not rows:
        # Distinguish "unknown series" from "known but not yet ingested".
        known = code in _PLAN_CODES or code in MACRO_SERIES_UNAVAILABLE
        if not known:
            raise HTTPException(status_code=404, detail=f"Unknown series: {series_code}")

    return MacroSeriesResponse(
        series_code=code,
        label=MACRO_SERIES_LABELS.get(code, code),
        unit=rows[-1].unit if rows else None,
        source=rows[-1].source if rows else None,
        observations=[
            MacroObservationOut(
                observation_date=r.observation_date,
                value=r.value,
                unit=r.unit,
                source=r.source,
            )
            for r in rows
        ],
    )
