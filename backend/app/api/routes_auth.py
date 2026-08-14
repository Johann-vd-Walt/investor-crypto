"""Auth endpoints (global TOTP gate). Not gated by the auth middleware."""

from __future__ import annotations

import time

from fastapi import APIRouter, Request
from pydantic import BaseModel

from app import auth
from app.config import get_settings

router = APIRouter(prefix="/api/auth", tags=["auth"])

# Tiny in-memory brute-force throttle (per-process): max attempts per window.
_MAX_ATTEMPTS = 6
_WINDOW_SECONDS = 60
_attempts: list[float] = []


class LoginRequest(BaseModel):
    code: str


class LoginResponse(BaseModel):
    token: str
    expires_in: int


class AuthStatus(BaseModel):
    enabled: bool
    authenticated: bool


@router.get("/status", response_model=AuthStatus)
def status(request: Request) -> AuthStatus:
    settings = get_settings()
    enabled = auth.is_enabled(settings)
    token = auth.bearer_token(request.headers.get("Authorization"))
    authed = (not enabled) or auth.verify_session_token(token, settings)
    return AuthStatus(enabled=enabled, authenticated=authed)


@router.post("/login")
def login(payload: LoginRequest):
    settings = get_settings()
    if not auth.is_enabled(settings):
        # Auth disabled — nothing to log into.
        return {"token": "", "expires_in": 0, "detail": "auth disabled"}

    now = time.time()
    _attempts[:] = [t for t in _attempts if now - t < _WINDOW_SECONDS]
    if len(_attempts) >= _MAX_ATTEMPTS:
        from fastapi import HTTPException
        raise HTTPException(status_code=429, detail="Too many attempts — wait a minute.")
    _attempts.append(now)

    if not auth.verify_totp(payload.code, settings):
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="Invalid code.")

    _attempts.clear()  # success resets the throttle
    token, ttl = auth.create_session_token(settings)
    return LoginResponse(token=token, expires_in=ttl)
