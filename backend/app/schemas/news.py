"""News response schemas (§11).

Sentiment is on a -1..1 scale (§8); it can be null when a provider gives none.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from app.schemas.common import DecimalAsFloat


class NewsArticleOut(BaseModel):
    id: int
    source: str
    url: str
    title: str
    snippet: str | None
    published_at: datetime | None
    language: str | None
    # Present on per-ticker responses (the sentiment for the queried security).
    entity_symbol: str | None = None
    sentiment: DecimalAsFloat | None = None
    relevance: DecimalAsFloat | None = None


class NewsListResponse(BaseModel):
    ticker: str | None = None
    count: int
    articles: list[NewsArticleOut]
