"""Prices + indicators endpoints (Section 11).

Prices are returned in RAND with explicit ``as_of`` and ``is_delayed`` fields.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.repositories import indicators as indicators_repo
from app.repositories import prices as prices_repo
from app.repositories import securities as securities_repo
from app.schemas.indicators import (
    IndicatorPoint,
    IndicatorsResponse,
    IndicatorSeries,
)
from app.schemas.prices import PriceBarOut, PriceSeriesResponse, cents_to_rand

router = APIRouter(prefix="/api", tags=["prices"])


def _resolve_security(db: Session, ticker: str):
    sec = securities_repo.get_by_ticker(db, ticker)
    if sec is None:
        raise HTTPException(status_code=404, detail=f"Unknown ticker: {ticker}")
    return sec


@router.get("/prices/{ticker}", response_model=PriceSeriesResponse)
def get_prices(
    ticker: str,
    timeframe: str = Query(default="1d"),
    from_: date | None = Query(default=None, alias="from"),
    to: date | None = Query(default=None),
    db: Session = Depends(get_db),
) -> PriceSeriesResponse:
    sec = _resolve_security(db, ticker)
    bars = prices_repo.get_bars(
        db, security_id=sec.id, timeframe=timeframe, start=from_, end=to
    )
    latest = prices_repo.get_latest_bar(db, security_id=sec.id, timeframe=timeframe)

    return PriceSeriesResponse(
        ticker=sec.ticker,
        timeframe=timeframe,
        as_of=latest.bar_datetime if latest else None,
        is_delayed=bool(latest.is_delayed) if latest else True,
        source=latest.source if latest else None,
        bars=[
            PriceBarOut(
                bar_datetime=b.bar_datetime,
                open=cents_to_rand(b.open),
                high=cents_to_rand(b.high),
                low=cents_to_rand(b.low),
                close=cents_to_rand(b.close),
                adj_close=cents_to_rand(b.adj_close),
                volume=b.volume,
            )
            for b in bars
        ],
    )


@router.get("/indicators/{ticker}", response_model=IndicatorsResponse)
def get_indicators(
    ticker: str,
    timeframe: str = Query(default="1d"),
    names: str | None = Query(default=None, description="Comma-separated, e.g. sma_20,rsi_14"),
    db: Session = Depends(get_db),
) -> IndicatorsResponse:
    sec = _resolve_security(db, ticker)
    name_list = [n.strip() for n in names.split(",")] if names else None
    rows = indicators_repo.get_values(
        db, security_id=sec.id, timeframe=timeframe, names=name_list
    )

    grouped: dict[str, list[IndicatorPoint]] = defaultdict(list)
    for r in rows:
        grouped[r.indicator].append(
            IndicatorPoint(bar_datetime=r.bar_datetime, value=r.value)
        )

    return IndicatorsResponse(
        ticker=sec.ticker,
        timeframe=timeframe,
        series=[
            IndicatorSeries(indicator=name, points=points)
            for name, points in grouped.items()
        ],
    )
