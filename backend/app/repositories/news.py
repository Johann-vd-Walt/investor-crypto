"""Data-access for news articles + sentiment (Guardrail 2.4).

Articles are deduplicated by ``url_hash = sha256(url)``. Sentiment rows link an
article to a security (per-ticker) or to nothing (security_id NULL = general
market news).
"""

from __future__ import annotations

import hashlib
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db.models import NewsArticle, NewsSentiment
from app.providers.base import Article


def url_hash(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


def upsert_article(db: Session, article: Article) -> tuple[NewsArticle, bool]:
    """Insert the article if new (by url_hash). Returns (row, created)."""
    h = url_hash(article.url)
    existing = db.scalar(select(NewsArticle).where(NewsArticle.url_hash == h))
    if existing is not None:
        return existing, False

    row = NewsArticle(
        source=article.source,
        url=article.url[:768],
        url_hash=h,
        title=article.title[:512],
        snippet=article.snippet,
        published_at=article.published_at,
        language=article.language,
        raw=article.raw,
    )
    db.add(row)
    db.flush()
    return row, True


def sentiment_exists(
    db: Session, *, article_id: int, security_id: int | None, entity_symbol: str | None
) -> bool:
    stmt = select(NewsSentiment.id).where(
        NewsSentiment.article_id == article_id,
        NewsSentiment.security_id.is_(security_id) if security_id is None
        else NewsSentiment.security_id == security_id,
    )
    if entity_symbol is None:
        stmt = stmt.where(NewsSentiment.entity_symbol.is_(None))
    else:
        stmt = stmt.where(NewsSentiment.entity_symbol == entity_symbol)
    return db.scalar(stmt) is not None


def add_sentiment(
    db: Session,
    *,
    article_id: int,
    security_id: int | None,
    entity_symbol: str | None,
    sentiment,
    relevance,
    model: str,
) -> None:
    """Add a sentiment row unless an identical one already exists (idempotent)."""
    if sentiment_exists(
        db, article_id=article_id, security_id=security_id, entity_symbol=entity_symbol
    ):
        return
    db.add(
        NewsSentiment(
            article_id=article_id,
            security_id=security_id,
            entity_symbol=entity_symbol,
            sentiment=sentiment,
            relevance=relevance,
            model=model,
        )
    )
    db.flush()


def list_for_security(
    db: Session, *, security_id: int, since: datetime | None = None, limit: int = 50
) -> list[tuple[NewsArticle, NewsSentiment]]:
    """Articles tagged with this security, newest first, with the sentiment row."""
    stmt = (
        select(NewsArticle, NewsSentiment)
        .join(NewsSentiment, NewsSentiment.article_id == NewsArticle.id)
        .where(NewsSentiment.security_id == security_id)
    )
    if since:
        stmt = stmt.where(NewsArticle.published_at >= since)
    stmt = stmt.order_by(NewsArticle.published_at.desc()).limit(limit)
    return list(db.execute(stmt).all())


def sentiment_pairs_for_security(
    db: Session, *, security_id: int, since: datetime | None = None
) -> list[tuple[float | None, float | None]]:
    """(sentiment, relevance) pairs for a security's recent news (for scoring)."""
    stmt = select(NewsSentiment.sentiment, NewsSentiment.relevance).where(
        NewsSentiment.security_id == security_id
    )
    if since:
        stmt = stmt.where(NewsSentiment.created_at >= since)
    return [
        (float(s) if s is not None else None, float(r) if r is not None else None)
        for s, r in db.execute(stmt).all()
    ]


def list_general(
    db: Session, *, since: datetime | None = None, limit: int = 50
) -> list[NewsArticle]:
    """General market news: articles with a security_id-NULL sentiment row."""
    stmt = (
        select(NewsArticle)
        .join(NewsSentiment, NewsSentiment.article_id == NewsArticle.id)
        .where(NewsSentiment.security_id.is_(None))
        .options(selectinload(NewsArticle.sentiments))
    )
    if since:
        stmt = stmt.where(NewsArticle.published_at >= since)
    stmt = stmt.order_by(NewsArticle.published_at.desc()).limit(limit).distinct()
    return list(db.scalars(stmt).all())
