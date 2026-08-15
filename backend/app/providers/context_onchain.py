"""Free on-chain & liquidity context series (keyless).

  - STABLE : aggregate stablecoin supply (USD bn) — "dry powder" — DeFiLlama
  - MVRV   : Bitcoin market-cap / realized-cap ratio — cycle valuation — Coin
             Metrics community API (computed from CapMrktCurUSD / CapRealUSD)

Both are slow-moving CONTEXT, informative mainly at cycle extremes — never swing
triggers. Keyless, free. Parsers pure for testing. Coin Metrics community data is
for non-commercial/personal use (fits this app).
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation

import httpx

from app.providers.base import MacroProvider, Observation

logger = logging.getLogger("app.providers.context_onchain")

_DEFILLAMA = "https://stablecoins.llama.fi/stablecoincharts/all"
_COINMETRICS = "https://community-api.coinmetrics.io/v4/timeseries/asset-metrics"
_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}


def parse_stablecoins(payload: list) -> list[tuple[date, Decimal]]:
    """DeFiLlama stablecoin chart -> [(date, total supply in USD bn)]."""
    out: list[tuple[date, Decimal]] = []
    for row in payload or []:
        if not isinstance(row, dict):
            continue
        ts = row.get("date")
        total = row.get("totalCirculatingUSD") or {}
        usd = total.get("peggedUSD") if isinstance(total, dict) else None
        if ts is None or usd is None:
            continue
        try:
            d = datetime.fromtimestamp(int(ts), tz=timezone.utc).date()
            out.append((d, (Decimal(str(usd)) / Decimal("1000000000")).quantize(Decimal("0.001"))))
        except (ValueError, TypeError, InvalidOperation):
            continue
    return out


def parse_mvrv(payload: dict) -> list[tuple[date, Decimal]]:
    """Coin Metrics asset-metrics -> [(date, MVRV = mkt/realized)]."""
    out: list[tuple[date, Decimal]] = []
    for row in (payload or {}).get("data", []) or []:
        t = row.get("time")
        mkt = row.get("CapMrktCurUSD")
        real = row.get("CapRealUSD")
        if not t or mkt is None or real is None:
            continue
        try:
            d = datetime.fromisoformat(t.replace("Z", "+00:00")).date()
            reald = Decimal(str(real))
            if reald == 0:
                continue
            out.append((d, (Decimal(str(mkt)) / reald).quantize(Decimal("0.0001"))))
        except (ValueError, TypeError, InvalidOperation):
            continue
    return out


class ContextOnchainProvider(MacroProvider):
    @property
    def name(self) -> str:
        return "onchain_free"

    def get_series(
        self, series_code: str, start: date | None = None, end: date | None = None
    ) -> list[Observation]:
        if series_code == "STABLE":
            return self._fetch(_DEFILLAMA, None, parse_stablecoins, "USD bn", start, end, "STABLE")
        if series_code == "MVRV":
            params = {
                "assets": "btc",
                "metrics": "CapMrktCurUSD,CapRealUSD",
                "frequency": "1d",
                "page_size": 10000,
            }
            return self._fetch(_COINMETRICS, params, parse_mvrv, "ratio", start, end, "MVRV")
        raise ValueError(f"ContextOnchainProvider has no series '{series_code}'.")

    def _fetch(self, url, params, parser, unit, start, end, code) -> list[Observation]:
        try:
            resp = httpx.get(url, params=params, headers=_HEADERS, timeout=40.0)
        except httpx.HTTPError as exc:
            self._record(endpoint=url, status_code=None, rows_returned=None, note=f"{code}: {exc}")
            raise
        if resp.status_code != 200:
            self._record(endpoint=url, status_code=resp.status_code, rows_returned=None, note=code)
            resp.raise_for_status()
        pairs = parser(resp.json())
        obs = [
            Observation(observation_date=d, value=v, unit=unit)
            for d, v in pairs
            if (start is None or d >= start) and (end is None or d <= end)
        ]
        self._record(endpoint=url, status_code=200, rows_returned=len(obs), note=code)
        return obs
