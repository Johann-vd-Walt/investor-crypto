"""Free, keyless context series.

  - STABLE : aggregate stablecoin supply (USD bn) — "dry powder" — DeFiLlama
  - MVRV   : Bitcoin market-cap / realized-cap ratio — cycle valuation —
             bitcoin-data.com (bgeometrics), keyless, full daily history
  - GOLD   : spot gold (USD/oz) — risk-regime backdrop — gold-api.com (keyless,
             current price only; a daily series builds up as the job runs)

All slow-moving CONTEXT, informative mainly at extremes — never swing triggers.
Keyless, free. Parsers pure for testing.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation

import httpx

from app.providers.base import MacroProvider, Observation

logger = logging.getLogger("app.providers.context_onchain")

_DEFILLAMA = "https://stablecoins.llama.fi/stablecoincharts/all"
_MVRV = "https://bitcoin-data.com/v1/mvrv"
_GOLD = "https://api.gold-api.com/price/XAU"
_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}


def parse_stablecoins(payload) -> list[tuple[date, Decimal]]:
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


def parse_mvrv(payload) -> list[tuple[date, Decimal]]:
    """bitcoin-data.com MVRV history [{d, mvrv}] -> [(date, ratio)]."""
    out: list[tuple[date, Decimal]] = []
    for row in payload or []:
        if not isinstance(row, dict):
            continue
        d_raw = row.get("d")
        v_raw = row.get("mvrv")
        if not d_raw or v_raw is None:
            continue
        try:
            d = datetime.strptime(str(d_raw)[:10], "%Y-%m-%d").date()
            out.append((d, Decimal(str(v_raw)).quantize(Decimal("0.0001"))))
        except (ValueError, TypeError, InvalidOperation):
            continue
    return out


def parse_gold(payload) -> list[tuple[date, Decimal]]:
    """gold-api.com current price {price, updatedAt} -> [(date, USD/oz)]."""
    if not isinstance(payload, dict) or payload.get("price") is None:
        return []
    try:
        px = Decimal(str(payload["price"])).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError, TypeError):
        return []
    upd = payload.get("updatedAt")
    try:
        d = datetime.fromisoformat(str(upd).replace("Z", "+00:00")).date() if upd else date.today()
    except (ValueError, TypeError):
        d = date.today()
    return [(d, px)]


class ContextOnchainProvider(MacroProvider):
    @property
    def name(self) -> str:
        return "context_free"

    def get_series(
        self, series_code: str, start: date | None = None, end: date | None = None
    ) -> list[Observation]:
        if series_code == "STABLE":
            return self._fetch(_DEFILLAMA, parse_stablecoins, "USD bn", start, end, "STABLE")
        if series_code == "MVRV":
            return self._fetch(_MVRV, parse_mvrv, "ratio", start, end, "MVRV")
        if series_code == "GOLD":
            return self._fetch(_GOLD, parse_gold, "USD/oz", start, end, "GOLD")
        raise ValueError(f"ContextOnchainProvider has no series '{series_code}'.")

    def _fetch(self, url, parser, unit, start, end, code) -> list[Observation]:
        try:
            resp = httpx.get(url, headers=_HEADERS, timeout=40.0)
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
