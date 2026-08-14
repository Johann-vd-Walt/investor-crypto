"""Abstract provider interfaces (Guardrail 2.5).

No provider-specific code may leak past these interfaces into the ingestion
job, signal engine, or API layer. Each concrete provider (Yahoo, EODHD, ...)
subclasses the relevant family interface.

Units (Guardrail 2.3): ``Bar`` prices are ALWAYS in canonical cents (ZAc).
Normalisation from a feed's native unit happens inside each provider's parser,
never downstream.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel

logger = logging.getLogger("app.providers")


class Bar(BaseModel):
    """One OHLCV daily bar. Prices in cents (ZAc)."""

    bar_datetime: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    adj_close: Decimal | None = None
    volume: int | None = None
    is_delayed: bool = True


@dataclass(slots=True)
class ProviderCallInfo:
    """One external call's outcome, destined for the ``provider_calls`` table."""

    provider: str
    endpoint: str | None
    status_code: int | None
    rows_returned: int | None
    note: str | None = None


# A sink the ingestion layer supplies so calls get persisted to provider_calls
# without the provider importing any DB code.
CallRecorder = Callable[[ProviderCallInfo], None]


class BaseProvider(ABC):
    """Common machinery: a name and a call-recording hook."""

    def __init__(self, call_recorder: CallRecorder | None = None) -> None:
        self._recorder = call_recorder

    @property
    @abstractmethod
    def name(self) -> str:
        """Short provider identifier, stored in ``source`` / ``provider``."""

    def _record(
        self,
        *,
        endpoint: str | None,
        status_code: int | None,
        rows_returned: int | None,
        note: str | None = None,
    ) -> None:
        info = ProviderCallInfo(
            provider=self.name,
            endpoint=endpoint,
            status_code=status_code,
            rows_returned=rows_returned,
            note=note,
        )
        if self._recorder is not None:
            try:
                self._recorder(info)
            except Exception:  # noqa: BLE001 — logging must never break ingestion
                logger.exception("Failed to record provider call for %s", self.name)


class PriceProvider(BaseProvider):
    """Daily OHLCV bars for a JSE ticker."""

    @abstractmethod
    def get_daily_bars(
        self, ticker: str, start: date | None = None, end: date | None = None
    ) -> list[Bar]:
        """Return daily bars for ``ticker`` in [start, end]. Prices in cents."""


# --- Interfaces for later phases (declared now for a stable contract) -------


class Observation(BaseModel):
    observation_date: date
    value: Decimal
    unit: str | None = None


class MacroProvider(BaseProvider):
    @abstractmethod
    def get_series(
        self, series_code: str, start: date | None = None, end: date | None = None
    ) -> list[Observation]:  # pragma: no cover - implemented in Phase 3
        ...


class CommodityProvider(BaseProvider):
    @abstractmethod
    def get_price(self, code: str) -> Observation:  # pragma: no cover - Phase 3
        ...


class ArticleEntity(BaseModel):
    """A security/entity tagged in an article, with its sentiment (-1..1)."""

    symbol: str | None = None
    name: str | None = None
    sentiment: Decimal | None = None
    relevance: Decimal | None = None


class Article(BaseModel):
    source: str
    url: str
    title: str
    snippet: str | None = None
    published_at: datetime | None = None
    language: str | None = None
    raw: dict | None = None
    entities: list[ArticleEntity] = []


class NewsProvider(BaseProvider):
    @abstractmethod
    def get_news(
        self, tickers: list[str], since: datetime | None = None
    ) -> list[Article]:  # pragma: no cover - implemented in Phase 4
        ...
