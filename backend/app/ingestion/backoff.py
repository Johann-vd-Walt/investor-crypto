"""Shared HTTP 429 backoff (Guardrail 2.6 — never hammer an API without backoff).

Retries a callable with exponential backoff only on HTTP 429 (rate limited);
any other error propagates immediately. ``sleep`` is injectable so tests don't
actually wait.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import TypeVar

import httpx

logger = logging.getLogger("app.ingestion.backoff")

T = TypeVar("T")


def call_with_backoff(
    fn: Callable[[], T],
    *,
    max_retries: int = 3,
    base: float = 2.0,
    label: str = "",
    sleep: Callable[[float], None] = time.sleep,
) -> T:
    attempt = 0
    while True:
        try:
            return fn()
        except httpx.HTTPStatusError as exc:
            resp = exc.response
            if resp is not None and resp.status_code == 429:
                attempt += 1
                if attempt > max_retries:
                    logger.warning("429 for %s: giving up after %d retries", label, attempt - 1)
                    raise
                wait = base ** attempt
                logger.warning("429 for %s: backing off %.0fs (attempt %d)", label, wait, attempt)
                sleep(wait)
                continue
            raise
