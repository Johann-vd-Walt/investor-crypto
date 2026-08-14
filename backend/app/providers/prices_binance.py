"""Binance daily price provider (public klines — no API key required).

Crypto market data from Binance's public data endpoint
(``data-api.binance.vision`` by default — no geo restrictions, no key). Prices
are stored in the pair's QUOTE currency (e.g. USDT) at native precision — there
is no cents convention.

Klines row shape (Binance): [openTime, open, high, low, close, volume,
closeTime, quoteVolume, trades, ...]. The parser is pure for fixture testing.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, time, timezone
from decimal import Decimal

import httpx

from app.config import get_settings
from app.providers.base import Bar, PriceProvider

logger = logging.getLogger("app.providers.binance")

_KLINES = "/api/v3/klines"
_MAX_LIMIT = 1000
_DAY_MS = 86_400_000


def parse_klines(rows: list) -> list[Bar]:
    """Parse Binance kline rows into daily Bars (native quote price)."""
    bars: list[Bar] = []
    for r in rows:
        try:
            open_ms = int(r[0])
            o, h, low, c, vol = r[1], r[2], r[3], r[4], r[5]
        except (IndexError, TypeError, ValueError):
            continue
        if c is None:
            continue
        d = datetime.fromtimestamp(open_ms / 1000, tz=timezone.utc).date()
        bars.append(
            Bar(
                bar_datetime=datetime.combine(d, time.min),
                open=Decimal(str(o)),
                high=Decimal(str(h)),
                low=Decimal(str(low)),
                close=Decimal(str(c)),
                adj_close=None,
                volume=int(float(vol)) if vol is not None else None,
                is_delayed=False,  # authoritative exchange data
            )
        )
    return bars


class BinancePriceProvider(PriceProvider):
    def __init__(self, call_recorder=None, base_url: str | None = None) -> None:
        super().__init__(call_recorder)
        self._base = (base_url or get_settings().binance_base_url).rstrip("/")

    @property
    def name(self) -> str:
        return "binance"

    def get_daily_bars(
        self, ticker: str, start: date | None = None, end: date | None = None
    ) -> list[Bar]:
        symbol = ticker.strip().upper()
        url = f"{self._base}{_KLINES}"
        start_ms = (
            int(datetime.combine(start, time.min, tzinfo=timezone.utc).timestamp() * 1000)
            if start else int(datetime(2017, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
        )
        end_ms = (
            int(datetime.combine(end, time.max, tzinfo=timezone.utc).timestamp() * 1000)
            if end else None
        )

        all_bars: list[Bar] = []
        cursor = start_ms
        pages = 0
        while True:
            params: dict[str, str | int] = {
                "symbol": symbol, "interval": "1d", "startTime": cursor, "limit": _MAX_LIMIT,
            }
            if end_ms:
                params["endTime"] = end_ms
            try:
                resp = httpx.get(url, params=params, timeout=30.0)
            except httpx.HTTPError as exc:
                self._record(endpoint=url, status_code=None, rows_returned=None, note=str(exc))
                raise
            if resp.status_code != 200:
                self._record(endpoint=url, status_code=resp.status_code, rows_returned=None, note=resp.text[:200])
                resp.raise_for_status()

            rows = resp.json()
            if not rows:
                break
            all_bars.extend(parse_klines(rows))
            pages += 1
            last_open = int(rows[-1][0])
            if len(rows) < _MAX_LIMIT or pages >= 30:
                break
            cursor = last_open + _DAY_MS

        # Drop the current (incomplete) UTC day's candle so signals use closed bars.
        today = datetime.now(timezone.utc).date()
        all_bars = [b for b in all_bars if b.bar_datetime.date() < today]

        self._record(endpoint=url, status_code=200, rows_returned=len(all_bars), note=f"{symbol} daily")
        return all_bars
