"""Crypto 'macro' provider: the Fear & Greed index + the BTC market series.

Replaces the JSE macro providers (oil/gold/rand/ALSI). Two series:
  - FNG : Crypto Fear & Greed index (0..100) from alternative.me (free, no key)
  - BTC : Bitcoin daily close (USDT) from Binance — the crypto 'market' proxy

Parsers are pure for fixture testing.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from decimal import Decimal

import httpx

from app.config import get_settings
from app.providers.base import MacroProvider, Observation
from app.providers.prices_binance import BinancePriceProvider

logger = logging.getLogger("app.providers.macro_crypto")


def parse_fng(payload: dict) -> list[Observation]:
    """Parse an alternative.me Fear & Greed payload into Observations (0..100)."""
    obs: list[Observation] = []
    for row in (payload or {}).get("data", []) or []:
        val = row.get("value")
        ts = row.get("timestamp")
        if val is None or ts is None:
            continue
        try:
            d = datetime.fromtimestamp(int(ts), tz=timezone.utc).date()
            obs.append(Observation(observation_date=d, value=Decimal(str(val)), unit="index 0-100"))
        except (ValueError, TypeError):
            continue
    return obs


class CryptoMacroProvider(MacroProvider):
    def __init__(self, call_recorder=None) -> None:
        super().__init__(call_recorder)
        self._settings = get_settings()

    @property
    def name(self) -> str:
        return "crypto_macro"

    def get_series(
        self, series_code: str, start: date | None = None, end: date | None = None
    ) -> list[Observation]:
        if series_code == "FNG":
            url = self._settings.fear_greed_url
            try:
                resp = httpx.get(url, params={"limit": 0, "format": "json"}, timeout=30.0)
            except httpx.HTTPError as exc:
                self._record(endpoint=url, status_code=None, rows_returned=None, note=str(exc))
                raise
            if resp.status_code != 200:
                self._record(endpoint=url, status_code=resp.status_code, rows_returned=None, note=resp.text[:200])
                resp.raise_for_status()
            obs = parse_fng(resp.json())
            obs = [o for o in obs if (start is None or o.observation_date >= start) and (end is None or o.observation_date <= end)]
            self._record(endpoint=url, status_code=200, rows_returned=len(obs), note="fear & greed")
            return obs

        if series_code == "BTC":
            # Reuse the Binance price provider; the market proxy is BTC's close.
            bars = BinancePriceProvider(self._recorder).get_daily_bars("BTCUSDT", start, end)
            return [
                Observation(observation_date=b.bar_datetime.date(), value=b.close, unit="USDT")
                for b in bars
            ]

        raise ValueError(f"CryptoMacroProvider has no series '{series_code}'.")
