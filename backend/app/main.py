"""FastAPI application factory and router registration.

Registers routers per phase and starts the in-process APScheduler on startup.
Later phases add macro, news, signals, trades, and paper routers here.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app import auth
from app.api import (
    routes_admin,
    routes_auth,
    routes_backtest,
    routes_bot,
    routes_consensus,
    routes_freshness,
    routes_health,
    routes_macro,
    routes_market,
    routes_news,
    routes_paper,
    routes_pine,
    routes_positioning,
    routes_prices,
    routes_securities,
    routes_security,
    routes_sens,
    routes_settings,
    routes_signals,
    routes_trades,
    routes_watchlist,
)
from app.config import get_settings
from app.ingestion.scheduler import shutdown_scheduler, start_scheduler

logger = logging.getLogger("app.main")


def _configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


# Paths reachable WITHOUT a session (login flow, health, API docs).
_AUTH_EXEMPT_PREFIXES = ("/api/auth/", "/docs", "/openapi.json", "/redoc")
_AUTH_EXEMPT_EXACT = {"/api/health"}


class AuthMiddleware(BaseHTTPMiddleware):
    """Gate every /api/* route behind the TOTP session, except the auth/health
    endpoints. No-op when auth is disabled (blank TOTP_SECRET)."""

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if (
            request.method == "OPTIONS"
            or not path.startswith("/api/")
            or path in _AUTH_EXEMPT_EXACT
            or any(path.startswith(p) for p in _AUTH_EXEMPT_PREFIXES)
            or not auth.is_enabled()
        ):
            return await call_next(request)

        token = auth.bearer_token(request.headers.get("Authorization"))
        if auth.verify_session_token(token):
            return await call_next(request)
        return JSONResponse({"detail": "Authentication required"}, status_code=401)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start the background scheduler; never let a scheduler failure block boot.
    try:
        start_scheduler()
    except Exception:  # noqa: BLE001
        logger.exception("Failed to start scheduler; continuing without it.")
    yield
    shutdown_scheduler()


def create_app() -> FastAPI:
    settings = get_settings()
    _configure_logging(settings.log_level)

    if settings.app_env == "production" and not auth.is_enabled(settings):
        logger.warning(
            "SECURITY: APP_ENV=production but the TOTP login is DISABLED — the app "
            "is OPEN to anyone who can reach it. Run `python -m app.auth_setup` and "
            "set TOTP_SECRET before exposing it to the internet."
        )

    # Don't expose the interactive docs / OpenAPI schema in production — no reason
    # to publish the full API surface to unauthenticated visitors. Available in dev.
    _docs = settings.app_env != "production"
    app = FastAPI(
        title="JSE Swing-Trading Decision-Support",
        version="0.1.0",
        description=(
            "Personal, decision-support only. Does NOT place trades. "
            "Signals are probabilistic estimates and can be wrong."
        ),
        lifespan=lifespan,
        docs_url="/docs" if _docs else None,
        redoc_url="/redoc" if _docs else None,
        openapi_url="/openapi.json" if _docs else None,
    )

    # Auth gate added first so CORS (added next) wraps its 401s with CORS headers.
    app.add_middleware(AuthMiddleware)

    # CORS for the Vite dev server.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_origin],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(routes_auth.router)
    app.include_router(routes_health.router)
    app.include_router(routes_freshness.router)
    app.include_router(routes_securities.router)
    app.include_router(routes_watchlist.router)
    app.include_router(routes_prices.router)
    app.include_router(routes_macro.router)
    app.include_router(routes_news.router)
    app.include_router(routes_signals.router)
    app.include_router(routes_sens.router)
    app.include_router(routes_paper.router)
    app.include_router(routes_trades.router)
    app.include_router(routes_backtest.router)
    app.include_router(routes_pine.router)
    app.include_router(routes_settings.router)
    app.include_router(routes_admin.router)
    app.include_router(routes_security.router)
    app.include_router(routes_positioning.router)
    app.include_router(routes_consensus.router)
    app.include_router(routes_bot.router)
    app.include_router(routes_market.router)
    return app


app = create_app()
