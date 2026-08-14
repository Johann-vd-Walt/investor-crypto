"""Auth endpoints (global TOTP gate). Not gated by the auth middleware."""

from __future__ import annotations

import time

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app import auth
from app.config import get_settings

router = APIRouter(prefix="/api/auth", tags=["auth"])

# Per-IP in-memory brute-force throttle. The app runs a single worker, so a
# process-local map is sufficient (no Redis needed). After _MAX_FAILURES bad
# codes from one IP within the window, that IP is locked out until the oldest
# failure ages out. A successful login clears that IP immediately. Being per-IP
# (not global) means an attacker hammering the endpoint cannot lock out the owner.
_MAX_FAILURES = 6
_WINDOW_SECONDS = 300
_failures: dict[str, list[float]] = {}


def _client_ip(request: Request) -> str:
    # uvicorn runs with --proxy-headers, so request.client.host is the real
    # client IP that nginx passed through in X-Forwarded-For.
    return request.client.host if request.client else "unknown"


def _prune(now: float) -> None:
    # Keep the map bounded: drop IPs whose failures have all aged out.
    for ip in list(_failures):
        fresh = [t for t in _failures[ip] if now - t < _WINDOW_SECONDS]
        if fresh:
            _failures[ip] = fresh
        else:
            _failures.pop(ip, None)


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
def login(payload: LoginRequest, request: Request):
    settings = get_settings()
    if not auth.is_enabled(settings):
        # Auth disabled — nothing to log into.
        return {"token": "", "expires_in": 0, "detail": "auth disabled"}

    ip = _client_ip(request)
    now = time.time()
    fails = [t for t in _failures.get(ip, []) if now - t < _WINDOW_SECONDS]

    if len(fails) >= _MAX_FAILURES:
        retry = max(1, int(_WINDOW_SECONDS - (now - min(fails))))
        raise HTTPException(
            status_code=429,
            detail="Too many failed attempts — try again shortly.",
            headers={"Retry-After": str(retry)},
        )

    if not auth.verify_totp(payload.code, settings):
        fails.append(now)
        _failures[ip] = fails
        _prune(now)
        raise HTTPException(status_code=401, detail="Invalid code.")

    _failures.pop(ip, None)  # success resets this IP's throttle
    token, ttl = auth.create_session_token(settings)
    return LoginResponse(token=token, expires_in=ttl)
