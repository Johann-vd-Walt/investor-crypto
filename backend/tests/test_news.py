"""Phase 4: Marketaux parser (fixture) + news endpoints (DB-backed).

The parser test needs no network. The endpoint test seeds an article via the
repository (the live Marketaux key was invalid during development) and cleans
up afterwards.
"""

import json
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import delete, select
from starlette.testclient import TestClient

from app.db.models import NewsArticle, NewsSentiment
from app.db.session import SessionLocal, check_db_connection
from app.main import app
from app.providers.news_marketaux import parse_news_response
from app.repositories import news as news_repo
from app.repositories import securities as securities_repo

FIX = Path(__file__).parent / "fixtures" / "marketaux_news.json"
client = TestClient(app)


# --- Parser (no network) ---

def test_parse_marketaux_articles_and_entities():
    articles = parse_news_response(json.loads(FIX.read_text()))
    assert len(articles) == 2

    npn = articles[0]
    assert npn.title.startswith("Naspers")
    assert npn.published_at is not None
    assert len(npn.entities) == 2
    assert npn.entities[0].symbol == "NPN.JSE"
    assert npn.entities[0].sentiment == Decimal("0.62")

    assert articles[1].entities == []  # general (no entities)


def test_parse_marketaux_error_raises():
    with pytest.raises(ValueError):
        parse_news_response({"error": {"code": "invalid_api_token"}})


# --- Endpoints (DB-backed) ---

pytestmark = pytest.mark.skipif(
    not check_db_connection()[0], reason="Database not reachable."
)

_TEST_URLS = [
    "https://news.example.com/naspers-rally",
    "https://news.example.com/rand-weakens",
]


@pytest.fixture
def seeded_news():
    """Seed one per-ticker and one general article; clean up after."""
    db = SessionLocal()
    articles = parse_news_response(json.loads(FIX.read_text()))
    asset = securities_repo.get_by_ticker(db, "BTCUSDT")
    try:
        # Per-asset article linked to BTCUSDT.
        a0, _ = news_repo.upsert_article(db, articles[0])
        news_repo.add_sentiment(
            db, article_id=a0.id, security_id=asset.id, entity_symbol="BTC",
            sentiment=Decimal("0.62"), relevance=Decimal("21.4"), model="marketaux",
        )
        # General article.
        a1, _ = news_repo.upsert_article(db, articles[1])
        news_repo.add_sentiment(
            db, article_id=a1.id, security_id=None, entity_symbol=None,
            sentiment=None, relevance=None, model="marketaux",
        )
        db.commit()
        yield
    finally:
        ids = list(
            db.scalars(select(NewsArticle.id).where(NewsArticle.url.in_(_TEST_URLS))).all()
        )
        if ids:
            db.execute(delete(NewsSentiment).where(NewsSentiment.article_id.in_(ids)))
            db.execute(delete(NewsArticle).where(NewsArticle.id.in_(ids)))
            db.commit()
        db.close()


def test_ticker_news_endpoint(seeded_news):
    resp = client.get("/api/news", params={"ticker": "BTCUSDT"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["ticker"] == "BTCUSDT"
    assert body["count"] >= 1
    art = next(a for a in body["articles"] if a["url"] == _TEST_URLS[0])
    assert art["entity_symbol"] == "BTC"
    assert isinstance(art["sentiment"], (int, float))  # number, not Decimal string


def test_general_news_endpoint(seeded_news):
    resp = client.get("/api/news/general")
    assert resp.status_code == 200
    assert any(a["url"] == _TEST_URLS[1] for a in resp.json()["articles"])


def test_ticker_news_unknown_404():
    assert client.get("/api/news", params={"ticker": "ZZZZ"}).status_code == 404
