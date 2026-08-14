"""News endpoints (Section 11).

GET /api/news?ticker=&since=&limit=   per-security news with sentiment
GET /api/news/general?since=&limit=   general market news
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.repositories import news as news_repo
from app.repositories import securities as securities_repo
from app.schemas.news import NewsArticleOut, NewsListResponse

router = APIRouter(prefix="/api/news", tags=["news"])


@router.get("/general", response_model=NewsListResponse)
def general_news(
    since: datetime | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> NewsListResponse:
    rows = news_repo.list_general(db, since=since, limit=limit)
    return NewsListResponse(
        ticker=None,
        count=len(rows),
        articles=[
            NewsArticleOut(
                id=a.id, source=a.source, url=a.url, title=a.title,
                snippet=a.snippet, published_at=a.published_at, language=a.language,
            )
            for a in rows
        ],
    )


@router.get("", response_model=NewsListResponse)
def ticker_news(
    ticker: str = Query(..., description="JSE ticker, e.g. NPN"),
    since: datetime | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> NewsListResponse:
    sec = securities_repo.get_by_ticker(db, ticker)
    if sec is None:
        raise HTTPException(status_code=404, detail=f"Unknown ticker: {ticker}")

    rows = news_repo.list_for_security(db, security_id=sec.id, since=since, limit=limit)
    return NewsListResponse(
        ticker=sec.ticker,
        count=len(rows),
        articles=[
            NewsArticleOut(
                id=article.id, source=article.source, url=article.url,
                title=article.title, snippet=article.snippet,
                published_at=article.published_at, language=article.language,
                entity_symbol=sent.entity_symbol, sentiment=sent.sentiment,
                relevance=sent.relevance,
            )
            for article, sent in rows
        ],
    )
