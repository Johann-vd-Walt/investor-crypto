"""Global TOTP authentication (single owner, no users/RBAC).

A single base32 TOTP secret (``TOTP_SECRET``) gates the whole app. Verifying a
6-digit code (Google Authenticator) issues a short-lived signed JWT the frontend
sends as ``Authorization: Bearer <token>``. If ``TOTP_SECRET`` is blank, auth is
DISABLED (open) so you can't be locked out before enrolling.
"""

from __future__ import annotations

import time

import jwt
import pyotp

from app.config import Settings, get_settings


def is_enabled(settings: Settings | None = None) -> bool:
    return bool((settings or get_settings()).totp_secret)


def _signing_key(settings: Settings) -> str:
    # Prefer an explicit key; else derive from the TOTP secret (stable across
    # restarts). Both blank only when auth is disabled anyway.
    return settings.auth_secret_key or settings.totp_secret or "insecure-dev-key"


def verify_totp(code: str, settings: Settings | None = None) -> bool:
    settings = settings or get_settings()
    if not settings.totp_secret:
        return False
    code = (code or "").strip().replace(" ", "")
    if not code.isdigit():
        return False
    # valid_window=1 tolerates ~30s clock drift either side.
    return pyotp.TOTP(settings.totp_secret).verify(code, valid_window=1)


def create_session_token(settings: Settings | None = None) -> tuple[str, int]:
    """Return (jwt, expires_in_seconds)."""
    settings = settings or get_settings()
    ttl = settings.session_ttl_hours * 3600
    now = int(time.time())
    token = jwt.encode(
        {"sub": "owner", "iat": now, "exp": now + ttl},
        _signing_key(settings),
        algorithm="HS256",
    )
    return token, ttl


def verify_session_token(token: str, settings: Settings | None = None) -> bool:
    settings = settings or get_settings()
    if not token:
        return False
    try:
        jwt.decode(token, _signing_key(settings), algorithms=["HS256"])
        return True
    except jwt.PyJWTError:
        return False


def bearer_token(authorization_header: str | None) -> str:
    if authorization_header and authorization_header.startswith("Bearer "):
        return authorization_header[7:].strip()
    return ""
