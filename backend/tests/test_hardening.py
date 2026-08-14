"""Phase 9: backoff helper (deterministic) + freshness endpoint."""

import httpx
import pytest
from starlette.testclient import TestClient

from app.db.session import check_db_connection
from app.ingestion.backoff import call_with_backoff
from app.main import app

client = TestClient(app)


def _http_error(status: int) -> httpx.HTTPStatusError:
    req = httpx.Request("GET", "https://example.test")
    resp = httpx.Response(status, request=req)
    return httpx.HTTPStatusError("boom", request=req, response=resp)


def test_backoff_retries_then_succeeds():
    calls = {"n": 0}
    waits: list[float] = []

    def fn():
        calls["n"] += 1
        if calls["n"] < 3:
            raise _http_error(429)
        return "ok"

    result = call_with_backoff(fn, base=2.0, label="t", sleep=waits.append)
    assert result == "ok"
    assert calls["n"] == 3
    assert waits == [2.0, 4.0]  # exponential, no real sleeping


def test_backoff_gives_up_after_max_retries():
    def fn():
        raise _http_error(429)

    with pytest.raises(httpx.HTTPStatusError):
        call_with_backoff(fn, max_retries=2, sleep=lambda _s: None)


def test_backoff_does_not_retry_non_429():
    calls = {"n": 0}

    def fn():
        calls["n"] += 1
        raise _http_error(500)

    with pytest.raises(httpx.HTTPStatusError):
        call_with_backoff(fn, sleep=lambda _s: None)
    assert calls["n"] == 1  # 500 is not retried


@pytest.mark.skipif(not check_db_connection()[0], reason="DB not reachable.")
def test_freshness_endpoint_shape():
    resp = client.get("/api/freshness")
    assert resp.status_code == 200
    body = resp.json()
    names = {f["name"] for f in body["families"]}
    assert names == {"prices", "macro", "news", "signals"}
    assert isinstance(body["overall_stale"], bool)
    for f in body["families"]:
        assert isinstance(f["stale"], bool)
        assert "count" in f
