"""Spot BTC/ETH ETF daily net-flow context via SoSoValue (free tier, needs key).

ETF net flows are among the more genuinely useful newer directional signals —
persistent multi-day inflows/outflows are decent confirmation (with a T+1 lag).
Stored as the aggregate daily net flow in USD millions (negative = net outflow).
Needs SOSOVALUE_API_KEY; disabled + surfaced honestly without one. Parser pure.

API (verified against sosovalue.gitbook.io):
  GET https://openapi.sosovalue.com/openapi/v1/etfs/summary-history
      ?symbol=BTC&country_code=US&limit=300
  header: x-soso-api-key: <KEY>
  -> { code, message, data:[{date:"YYYY-MM-DD", total_net_inflow:<USD>, ...}] }
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

import httpx

from app.providers.base import MacroProvider, Observation

logger = logging.getLogger("app.providers.context_etf")

_BASE = "https://openapi.sosovalue.com/openapi/v1/etfs/summary-history"

# our series code -> SoSoValue symbol
_SYMBOLS = {"ETF_FLOW": "BTC", "ETF_FLOW_ETH": "ETH"}


def parse_summary(payload) -> list[tuple[date, Decimal]]:
    """SoSoValue summary-history -> [(date, net flow USD millions)].

    Handles both the enveloped ({data:[...]}) and bare-array response shapes.
    """
    rows = payload
    if isinstance(payload, dict):
        rows = payload.get("data", [])
    out: list[tuple[date, Decimal]] = []
    for r in rows or []:
        if not isinstance(r, dict):
            continue
        d_raw = r.get("date")
        v_raw = r.get("total_net_inflow")
        if not d_raw or v_raw is None:
            continue
        try:
            d = datetime.strptime(str(d_raw)[:10], "%Y-%m-%d").date()
            usd_m = (Decimal(str(v_raw)) / Decimal("1000000")).quantize(Decimal("0.001"))
            out.append((d, usd_m))
        except (ValueError, InvalidOperation):
            continue
    return out


class SoSoValueEtfProvider(MacroProvider):
    def __init__(self, api_key: str, call_recorder=None) -> None:
        super().__init__(call_recorder)
        self._key = api_key

    @property
    def name(self) -> str:
        return "sosovalue"

    def get_series(
        self, series_code: str, start: date | None = None, end: date | None = None
    ) -> list[Observation]:
        symbol = _SYMBOLS.get(series_code)
        if symbol is None:
            raise ValueError(f"SoSoValueEtfProvider has no series '{series_code}'.")
        params = {"symbol": symbol, "country_code": "US", "limit": 300}
        try:
            resp = httpx.get(_BASE, params=params, headers={"x-soso-api-key": self._key}, timeout=20.0)
        except httpx.HTTPError as exc:
            self._record(endpoint=_BASE, status_code=None, rows_returned=None, note=f"{symbol}: {exc}")
            raise
        if resp.status_code != 200:
            self._record(endpoint=_BASE, status_code=resp.status_code, rows_returned=None, note=f"{symbol}: {resp.text[:120]}")
            resp.raise_for_status()
        pairs = parse_summary(resp.json())
        obs = [
            Observation(observation_date=d, value=v, unit="USD m/day")
            for d, v in pairs
            if (start is None or d >= start) and (end is None or d <= end)
        ]
        self._record(endpoint=_BASE, status_code=200, rows_returned=len(obs), note=f"{series_code}/{symbol}")
        return obs
