"""TOTP auth gate: token logic (pure) + middleware behaviour."""

import pyotp
import pytest
from starlette.testclient import TestClient

from app import auth
from app.config import Settings
from app.main import app

client = TestClient(app)


def _settings_with_secret(secret: str) -> Settings:
    return Settings(_env_file=None).model_copy(update={"totp_secret": secret})


def test_disabled_when_no_secret():
    s = Settings(_env_file=None).model_copy(update={"totp_secret": ""})
    assert auth.is_enabled(s) is False
    assert auth.verify_totp("123456", s) is False


def test_totp_verify_and_token_roundtrip():
    secret = pyotp.random_base32()
    s = _settings_with_secret(secret)
    assert auth.is_enabled(s) is True

    good = pyotp.TOTP(secret).now()
    assert auth.verify_totp(good, s) is True
    assert auth.verify_totp("000000", s) is False  # (astronomically unlikely to match)

    token, ttl = auth.create_session_token(s)
    assert ttl > 0
    assert auth.verify_session_token(token, s) is True
    assert auth.verify_session_token("garbage", s) is False
    # A token signed under a different secret must not validate.
    other = _settings_with_secret(pyotp.random_base32())
    assert auth.verify_session_token(token, other) is False


def test_bearer_parsing():
    assert auth.bearer_token("Bearer abc.def") == "abc.def"
    assert auth.bearer_token("Token abc") == ""
    assert auth.bearer_token(None) == ""


def test_auth_status_endpoint_open_when_disabled():
    # With no TOTP_SECRET in the test env, the gate is disabled -> open.
    body = client.get("/api/auth/status").json()
    assert body["enabled"] is False
    assert body["authenticated"] is True
    # And a protected endpoint is reachable without a token.
    assert client.get("/api/health").status_code == 200


def test_login_disabled_returns_noop():
    resp = client.post("/api/auth/login", json={"code": "123456"})
    assert resp.status_code == 200
    assert resp.json()["token"] == ""
