"""Phase 0 tests for the health endpoint.

The DB is not required to be up: /api/health must return 200 and report the
DB status either way (Guardrail 2.7 — surface failures, never crash).
"""

from starlette.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_returns_200_and_shape() -> None:
    resp = client.get("/api/health")
    assert resp.status_code == 200

    body = resp.json()
    assert body["status"] in {"ok", "degraded"}
    assert "database" in body
    assert isinstance(body["database"]["connected"], bool)
    assert "providers" in body
    # All four provider keys are reported (enabled or not).
    assert set(body["providers"]) == {
        "EODHD_API_KEY",
        "ALPHAVANTAGE_API_KEY",
        "MARKETAUX_API_KEY",
        "OILPRICE_API_KEY",
    }


def test_health_status_matches_db_connection() -> None:
    body = client.get("/api/health").json()
    connected = body["database"]["connected"]
    assert body["status"] == ("ok" if connected else "degraded")
