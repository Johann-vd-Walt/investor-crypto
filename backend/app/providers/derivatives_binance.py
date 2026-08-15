"""Binance USDⓈ-M futures positioning provider (Tier 1 — free, no key).

Pulls the four highest-value derivatives metrics for a perp symbol:
  - funding      : perpetual funding rate (real-money crowding gauge)
  - open_interest: total OI in USD (leverage committed)
  - long_short_pos: top-trader long/short POSITION ratio (smart-money lean)
  - taker_ratio  : taker buy/sell volume ratio (aggressor flow)

Host is fapi.binance.com (different from the spot data host). Some servers
geo-block it; every metric is fetched independently and a failure is recorded
and skipped, never raised — the app simply shows less. Parsers are pure.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

import httpx

from app.config import get_settings
from app.providers.base import BaseProvider

logger = logging.getLogger("app.providers.derivatives")

# metric -> (path, is_futures_data_dir, value_field, time_field)
_ENDPOINTS: dict[str, tuple[str, str, str]] = {
    "funding": ("/fapi/v1/fundingRate", "fundingRate", "fundingTime"),
    "open_interest": ("/futures/data/openInterestHist", "sumOpenInterestValue", "timestamp"),
    "long_short_pos": ("/futures/data/topLongShortPositionRatio", "longShortRatio", "timestamp"),
    "taker_ratio": ("/futures/data/takerlongshortRatio", "buySellRatio", "timestamp"),
}


def _to_dt(ms) -> datetime | None:
    try:
        return datetime.fromtimestamp(int(ms) / 1000, tz=timezone.utc).replace(tzinfo=None)
    except (ValueError, TypeError):
        return None


def _to_dec(v) -> Decimal | None:
    if v is None:
        return None
    try:
        return Decimal(str(v))
    except (InvalidOperation, ValueError, TypeError):
        return None


def parse_rows(rows: list, value_field: str, time_field: str) -> list[tuple[datetime, Decimal]]:
    """Pure parser: [{...}] -> [(ts, value)] dropping malformed rows."""
    out: list[tuple[datetime, Decimal]] = []
    for r in rows or []:
        if not isinstance(r, dict):
            continue
        ts = _to_dt(r.get(time_field))
        val = _to_dec(r.get(value_field))
        if ts is not None and val is not None:
            out.append((ts, val))
    return out


class BinanceDerivativesProvider(BaseProvider):
    def __init__(self, call_recorder=None, base_url: str | None = None) -> None:
        super().__init__(call_recorder)
        self._base = (base_url or get_settings().binance_futures_base_url).rstrip("/")

    @property
    def name(self) -> str:
        return "binance_futures"

    def get_metrics(
        self, symbol: str, *, funding_limit: int = 1000, hist_period: str = "1d", hist_limit: int = 30
    ) -> dict[str, list[tuple[datetime, Decimal]]]:
        """Return {metric: [(ts, value), ...]} for one perp symbol.

        Each metric is fetched independently; a failure records the call and
        yields an empty list for that metric rather than aborting the rest.
        """
        symbol = symbol.strip().upper()
        result: dict[str, list[tuple[datetime, Decimal]]] = {}
        for metric, (path, value_field, time_field) in _ENDPOINTS.items():
            url = f"{self._base}{path}"
            if metric == "funding":
                params: dict[str, str | int] = {"symbol": symbol, "limit": funding_limit}
            else:
                params = {"symbol": symbol, "period": hist_period, "limit": hist_limit}
            try:
                resp = httpx.get(url, params=params, timeout=20.0)
            except httpx.HTTPError as exc:
                self._record(endpoint=url, status_code=None, rows_returned=None, note=f"{symbol} {metric}: {exc}")
                result[metric] = []
                continue
            if resp.status_code != 200:
                self._record(endpoint=url, status_code=resp.status_code, rows_returned=None, note=f"{symbol} {metric}: {resp.text[:120]}")
                result[metric] = []
                continue
            parsed = parse_rows(resp.json(), value_field, time_field)
            self._record(endpoint=url, status_code=200, rows_returned=len(parsed), note=f"{symbol} {metric}")
            result[metric] = parsed
        return result
