"""APScheduler setup (Section 9).

In-process background scheduler — sufficient at this scale. Cadences follow §9.
Only ``ingest_daily_prices`` is scheduled in Phase 2; more jobs are added in
later phases. A single job failure must never kill the scheduler.
"""

from __future__ import annotations

import logging

from apscheduler.schedulers.background import BackgroundScheduler

from app.ingestion.jobs import (
    compute_indicators,
    generate_signals,
    ingest_daily_prices,
    ingest_macro,
    ingest_news,
    ingest_sens,
    update_paper_trades,
)

logger = logging.getLogger("app.scheduler")

# JSE closes ~17:00 SAST; ingest after close. Server tz may differ — this uses
# the process local time. Adjust the trigger's timezone if deploying elsewhere.
_scheduler: BackgroundScheduler | None = None


def _safe_ingest_daily_prices() -> None:
    try:
        summary = ingest_daily_prices()
        logger.info("Scheduled ingest_daily_prices summary: %s", summary)
    except Exception:  # noqa: BLE001 — never let a job kill the scheduler
        logger.exception("Scheduled ingest_daily_prices crashed")


def _safe_ingest_macro() -> None:
    try:
        summary = ingest_macro()
        logger.info("Scheduled ingest_macro summary: %s", summary)
    except Exception:  # noqa: BLE001
        logger.exception("Scheduled ingest_macro crashed")


def _safe_ingest_news() -> None:
    try:
        summary = ingest_news()
        logger.info("Scheduled ingest_news summary: %s", summary)
    except Exception:  # noqa: BLE001
        logger.exception("Scheduled ingest_news crashed")


def _safe_ingest_sens() -> None:
    try:
        summary = ingest_sens()
        logger.info("Scheduled ingest_sens summary: %s", summary)
    except Exception:  # noqa: BLE001
        logger.exception("Scheduled ingest_sens crashed")


def _safe_nightly_engine() -> None:
    """Nightly: update paper trades, recompute indicators, generate signals."""
    try:
        logger.info("Nightly update_paper_trades: %s", update_paper_trades())
        logger.info("Nightly compute_indicators: %s", compute_indicators())
        logger.info("Nightly generate_signals: %s", generate_signals())
    except Exception:  # noqa: BLE001
        logger.exception("Nightly engine run crashed")


def start_scheduler() -> BackgroundScheduler:
    global _scheduler
    if _scheduler is not None:
        return _scheduler

    # Pinned to SAST so the cron hours below mean the same thing no matter what
    # the server's clock is set to (a VPS usually defaults to UTC).
    scheduler = BackgroundScheduler(daemon=True, timezone="Africa/Johannesburg")
    # Crypto trades 24/7 — no weekday restriction. Daily bars close at 00:00 UTC
    # (02:00 SAST), so the 02:15 price pull still lands just after the close.
    # All hours below are SAST.
    scheduler.add_job(
        _safe_ingest_daily_prices, trigger="cron", hour=2, minute=15,
        id="ingest_daily_prices", replace_existing=True, misfire_grace_time=3600,
    )
    # Market regime (BTC) + Fear & Greed, a few times a day.
    scheduler.add_job(
        _safe_ingest_macro, trigger="cron", hour="2,10,18", minute=20,
        id="ingest_macro", replace_existing=True, misfire_grace_time=3600,
    )
    # Optional crypto news hourly.
    scheduler.add_job(
        _safe_ingest_news, trigger="cron", minute=30,
        id="ingest_news", replace_existing=True, misfire_grace_time=1800,
    )
    # News RSS hourly (offset).
    scheduler.add_job(
        _safe_ingest_sens, trigger="cron", minute=45,
        id="ingest_sens", replace_existing=True, misfire_grace_time=1800,
    )
    # Daily engine: update paper trades, recompute indicators, generate signals.
    scheduler.add_job(
        _safe_nightly_engine, trigger="cron", hour=3, minute=0,
        id="nightly_engine", replace_existing=True, misfire_grace_time=3600,
    )
    scheduler.start()
    _scheduler = scheduler
    logger.info(
        "APScheduler started, timezone=Africa/Johannesburg (SAST): "
        "prices @02:15; macro @02/10/18; news+rss hourly; engine @03:00 daily."
    )
    return scheduler


def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("APScheduler stopped.")
