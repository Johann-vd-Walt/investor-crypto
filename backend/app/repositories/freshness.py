"""Data-freshness queries (Guardrail 2.7 — surface staleness, never hide it)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import MacroSeries, NewsArticle, PriceBar, Signal


@dataclass
class FamilyFreshness:
    name: str
    last_ingest: datetime | None   # when we last pulled/wrote
    latest_data: datetime | None   # recency of the data itself
    count: int


def _scalar(db: Session, stmt):
    return db.scalar(stmt)


def get_freshness(db: Session) -> list[FamilyFreshness]:
    prices_count = db.scalar(select(func.count()).select_from(PriceBar)) or 0
    macro_count = db.scalar(select(func.count()).select_from(MacroSeries)) or 0
    news_count = db.scalar(select(func.count()).select_from(NewsArticle)) or 0
    signals_count = db.scalar(select(func.count()).select_from(Signal)) or 0

    return [
        FamilyFreshness(
            name="prices",
            last_ingest=db.scalar(select(func.max(PriceBar.ingested_at))),
            latest_data=db.scalar(select(func.max(PriceBar.bar_datetime))),
            count=prices_count,
        ),
        FamilyFreshness(
            name="macro",
            last_ingest=db.scalar(select(func.max(MacroSeries.ingested_at))),
            latest_data=None,  # observation_date is a DATE; last_ingest is the signal
            count=macro_count,
        ),
        FamilyFreshness(
            name="news",
            last_ingest=db.scalar(select(func.max(NewsArticle.fetched_at))),
            latest_data=db.scalar(select(func.max(NewsArticle.published_at))),
            count=news_count,
        ),
        FamilyFreshness(
            name="signals",
            last_ingest=db.scalar(select(func.max(Signal.generated_at))),
            latest_data=db.scalar(select(func.max(Signal.generated_at))),
            count=signals_count,
        ),
    ]
