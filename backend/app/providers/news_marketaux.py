"""Marketaux news + sentiment provider (Phase 4).

*** UNVERIFIED ***: during development the supplied MARKETAUX_API_KEY returned
HTTP 401 invalid_api_token, so this parser was written against Marketaux's
documented response shape (PROJECT_SPEC §8) and NOT confirmed against a live
response. Confirm the shape once a valid key is in place. The parser is pure
and defensive so it degrades gracefully on unexpected fields.

Documented shape of GET https://api.marketaux.com/v1/news/all :
    { "meta": {...},
      "data": [ { "uuid","title","description","snippet","url","language",
                  "published_at","source",
                  "entities": [ {"symbol","name","sentiment_score",
                                 "match_score", ...} ] } ] }

Sentiment (`sentiment_score`) is on a -1..1 scale per §8.
"""

from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal, InvalidOperation

import httpx

from app.providers.base import Article, ArticleEntity, NewsProvider

logger = logging.getLogger("app.providers.marketaux")

_URL = "https://api.marketaux.com/v1/news/all"


def _to_decimal(value) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _parse_published(value) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def parse_news_response(payload: dict) -> list[Article]:
    """Parse a Marketaux /news/all payload into Articles. Skips entries with no
    URL or title (never fabricates). Raises on an explicit API error object."""
    if not isinstance(payload, dict):
        raise ValueError("Marketaux returned a non-object response.")
    err = payload.get("error")
    if err:
        raise ValueError(f"Marketaux error: {err}")

    articles: list[Article] = []
    for row in payload.get("data") or []:
        url = row.get("url")
        title = row.get("title")
        if not url or not title:
            continue
        entities = [
            ArticleEntity(
                symbol=e.get("symbol"),
                name=e.get("name"),
                sentiment=_to_decimal(e.get("sentiment_score")),
                relevance=_to_decimal(e.get("match_score")),
            )
            for e in (row.get("entities") or [])
            if isinstance(e, dict)
        ]
        articles.append(
            Article(
                source=row.get("source") or "marketaux",
                url=url,
                title=title,
                snippet=row.get("snippet") or row.get("description"),
                published_at=_parse_published(row.get("published_at")),
                language=row.get("language"),
                raw=row,
                entities=entities,
            )
        )
    return articles


class MarketauxNewsProvider(NewsProvider):
    def __init__(self, api_key: str, call_recorder=None) -> None:
        super().__init__(call_recorder)
        self._api_key = api_key

    @property
    def name(self) -> str:
        return "marketaux"

    def get_news(self, tickers: list[str], since: datetime | None = None) -> list[Article]:
        params: dict[str, str | int] = {
            "language": "en",
            "limit": 3,  # free tier returns few per call; keep it explicit
            "api_token": self._api_key,
        }
        if tickers:
            # Marketaux tags JSE entities with the .JO suffix (confirmed via
            # entity search 2026-07-20 — e.g. SOL.JO, country 'za'). NOT .JSE.
            params["symbols"] = ",".join(f"{t.upper()}.JO" for t in tickers)
            params["filter_entities"] = "true"
        else:
            # General market news: focus on South Africa to avoid global noise.
            params["countries"] = "za"
        if since:
            params["published_after"] = since.strftime("%Y-%m-%dT%H:%M")

        try:
            resp = httpx.get(_URL, params=params, timeout=30.0)
        except httpx.HTTPError as exc:
            self._record(endpoint=_URL, status_code=None, rows_returned=None, note=str(exc))
            raise

        if resp.status_code != 200:
            self._record(
                endpoint=_URL, status_code=resp.status_code, rows_returned=None,
                note=resp.text[:200],
            )
            resp.raise_for_status()

        articles = parse_news_response(resp.json())
        self._record(
            endpoint=_URL, status_code=200, rows_returned=len(articles),
            note=f"news for {tickers or 'general'}",
        )
        return articles
