"""Crypto news RSS parser (fixture) + endpoint (DB-backed)."""

from pathlib import Path

import pytest
from sqlalchemy import delete
from starlette.testclient import TestClient

from app.db.models import SensAnnouncement
from app.db.session import SessionLocal, check_db_connection
from app.ingestion.jobs import _match_security, _sec_index
from app.main import app
from app.providers.sens_rss import parse_sens_rss

FIX = Path(__file__).parent / "fixtures" / "sens_feed.xml"
client = TestClient(app)


def test_parse_rss_skips_malformed_and_parses_dates():
    items = parse_sens_rss(FIX.read_text())
    assert len(items) == 2  # the link-less item is skipped
    first = items[0]
    assert "Bitcoin" in first.headline
    assert first.category == "Markets"
    assert first.published_at is not None
    assert first.published_at.tzinfo is None  # stored naive


def test_parse_rss_bad_xml_raises():
    with pytest.raises(ValueError):
        parse_sens_rss("not xml at all")


def test_match_security_by_name():
    index = [(1, "BTCUSDT", "bitcoin"), (2, "ETHUSDT", "ethereum")]
    assert _match_security("Bitcoin ETF sees record inflows", index) == 1
    assert _match_security("Ethereum upgrade goes live", index) == 2
    assert _match_security("Some Unknown Coin - notice", index) is None


@pytest.mark.skipif(not check_db_connection()[0], reason="DB not reachable.")
def test_news_matching_uses_real_assets_and_endpoint():
    db = SessionLocal()
    created = []
    try:
        index = _sec_index(db)  # real crypto assets (BTCUSDT should exist)
        btc_id = _match_security("Bitcoin ETF sees record inflows", index)
        assert btc_id is not None

        from datetime import datetime

        from app.repositories import sens as sens_repo

        row, _c = sens_repo.upsert(
            db, source="test", url="https://news.example.com/test-btc",
            headline="Bitcoin - Test", summary="x", category="Test",
            published_at=datetime(2026, 7, 15), security_id=btc_id, raw={},
        )
        db.commit()
        created.append(row.id)

        resp = client.get("/api/sens", params={"ticker": "BTCUSDT"})
        assert resp.status_code == 200
        assert any(i["url"] == "https://news.example.com/test-btc" for i in resp.json()["items"])

        assert client.get("/api/sens", params={"ticker": "ZZZZ"}).status_code == 404
    finally:
        if created:
            db.execute(delete(SensAnnouncement).where(SensAnnouncement.id.in_(created)))
            db.commit()
        db.close()
