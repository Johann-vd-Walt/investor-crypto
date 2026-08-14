"""Phase 8: settings service + endpoints (DB-backed)."""

from decimal import Decimal

import pytest
from starlette.testclient import TestClient

from app.db.models import AppConfig
from app.db.session import SessionLocal, check_db_connection
from app.main import app
from app.services import settings as settings_service

client = TestClient(app)

pytestmark = pytest.mark.skipif(not check_db_connection()[0], reason="DB not reachable.")


def _wipe_overrides():
    db = SessionLocal()
    try:
        db.query(AppConfig).delete()
        db.commit()
    finally:
        db.close()


@pytest.fixture(autouse=True)
def _clean_overrides():
    """Ensure a clean overrides table before AND after each test, so neither
    leftover state nor test order can pollute the effective-settings defaults."""
    _wipe_overrides()
    yield
    _wipe_overrides()


def test_effective_settings_defaults_then_override():
    db = SessionLocal()
    try:
        base = settings_service.get_effective_settings(db)
        assert base.buy_threshold == 0.3  # env default

        settings_service.set_overrides(db, {"buy_threshold": 0.45, "account_size": "250000"})
        db.commit()
        eff = settings_service.get_effective_settings(db)
        assert eff.buy_threshold == 0.45
        assert eff.account_size == Decimal("250000")
    finally:
        db.close()


def test_set_overrides_rejects_unknown_key():
    db = SessionLocal()
    try:
        with pytest.raises(ValueError):
            settings_service.set_overrides(db, {"not_a_setting": 1})
    finally:
        db.close()


def test_settings_endpoints_roundtrip():
    get1 = client.get("/api/settings")
    assert get1.status_code == 200
    assert "providers" in get1.json()

    put = client.put("/api/settings", json={"overrides": {"buy_threshold": 0.5}})
    assert put.status_code == 200
    body = put.json()
    assert body["buy_threshold"] == 0.5
    assert body["overrides"]["buy_threshold"] == 0.5
    # weights_ok reflects the weight-sum sanity check.
    assert isinstance(body["weights_ok"], bool)


def test_settings_endpoint_rejects_unknown():
    assert client.put("/api/settings", json={"overrides": {"bogus": 1}}).status_code == 400
