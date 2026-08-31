"""SQLAlchemy engine and session management.

Guardrail (Section 2.4): all DB access goes through this data-access layer.
The engine is created lazily and pooled; ``get_db`` is the FastAPI dependency
that yields a session and always closes it.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings

logger = logging.getLogger("app.db")


class Base(DeclarativeBase):
    """Declarative base for all ORM models (populated in Phase 1)."""


_settings = get_settings()

# pool_pre_ping guards against MySQL dropping idle connections. echo stays off;
# turn on via SQLAlchemy logging if needed.
engine = create_engine(
    _settings.database_url,
    pool_pre_ping=True,
    future=True,
)

SessionLocal = sessionmaker(
    bind=engine, autoflush=False, autocommit=False, expire_on_commit=False
)


# Store and read every timestamp in UTC. MySQL TIMESTAMP / CURRENT_TIMESTAMP
# columns are converted to the connection's ``time_zone`` on read; left at the
# server default (SYSTEM = SAST here) they come back 2h ahead of the app's own
# ``datetime.utcnow()`` values, so the two clocks disagree. Pinning the session
# to UTC makes every timestamp the app sees UTC-naive and consistent; the
# frontend then renders them in SAST. (TIMESTAMP columns are stored as UTC
# internally, so this is a safe reinterpretation of existing rows.)
if engine.dialect.name == "mysql":

    @event.listens_for(engine, "connect")
    def _set_session_utc(dbapi_conn, _record) -> None:  # noqa: ANN001
        with dbapi_conn.cursor() as cur:
            cur.execute("SET time_zone = '+00:00'")


def get_db() -> Iterator[Session]:
    """FastAPI dependency: yield a session, always close it."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def check_db_connection() -> tuple[bool, str | None]:
    """Return ``(ok, error)``. Never raises — used by /api/health.

    Guardrail (Section 2.7): surface failures rather than hiding them.
    """
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True, None
    except Exception as exc:  # noqa: BLE001 — health check must swallow all
        logger.warning("Database health check failed: %s", exc)
        return False, str(exc)
