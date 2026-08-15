"""Traditional-market macro series via FRED (St. Louis Fed) — free, needs a key.

Provides the risk-regime backdrop: broad US Dollar index, gold, US 10y yield,
S&P 500. These correlate with crypto in regime-dependent, unstable ways — useful
as context/filter, not timing signals. FRED is the stable, free source; a free
key is required (https://fred.stlouisfed.org/docs/api/api_key.html). Without a
key this layer is simply disabled and surfaced honestly. Parser is pure.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

import httpx

from app.providers.base import MacroProvider, Observation

logger = logging.getLogger("app.providers.macro_market")

_BASE = "https://api.stlouisfed.org/fred/series/observations"

# our series code -> FRED series id (gold is sourced keyless elsewhere)
_SERIES: dict[str, str] = {
    "DXY": "DTWEXBGS",   # Nominal Broad USD Index (proxy for ICE DXY)
    "US10Y": "DGS10",    # 10-Year Treasury yield (%)
    "SP500": "SP500",    # S&P 500 index level
}
_UNITS: dict[str, str] = {"DXY": "index", "US10Y": "%", "SP500": "index"}


def parse_fred(payload: dict) -> list[tuple[date, Decimal]]:
    """FRED observations payload -> [(date, value)]; skips '.' (missing) rows."""
    out: list[tuple[date, Decimal]] = []
    for row in (payload or {}).get("observations", []) or []:
        d_raw = (row.get("date") or "").strip()
        v_raw = (row.get("value") or "").strip()
        if not d_raw or v_raw in ("", "."):
            continue
        try:
            out.append((datetime.strptime(d_raw, "%Y-%m-%d").date(), Decimal(v_raw)))
        except (ValueError, InvalidOperation):
            continue
    return out


class FredMarketProvider(MacroProvider):
    def __init__(self, api_key: str, call_recorder=None) -> None:
        super().__init__(call_recorder)
        self._key = api_key

    @property
    def name(self) -> str:
        return "fred"

    def get_series(
        self, series_code: str, start: date | None = None, end: date | None = None
    ) -> list[Observation]:
        sid = _SERIES.get(series_code)
        if sid is None:
            raise ValueError(f"FredMarketProvider has no series '{series_code}'.")
        params = {"series_id": sid, "api_key": self._key, "file_type": "json"}
        if start:
            params["observation_start"] = start.isoformat()
        try:
            resp = httpx.get(_BASE, params=params, timeout=30.0)
        except httpx.HTTPError as exc:
            self._record(endpoint=_BASE, status_code=None, rows_returned=None, note=f"{sid}: {exc}")
            raise
        if resp.status_code != 200:
            self._record(endpoint=_BASE, status_code=resp.status_code, rows_returned=None, note=sid)
            resp.raise_for_status()
        pairs = parse_fred(resp.json())
        unit = _UNITS.get(series_code)
        obs = [
            Observation(observation_date=d, value=v, unit=unit)
            for d, v in pairs
            if (end is None or d <= end)
        ]
        self._record(endpoint=_BASE, status_code=200, rows_returned=len(obs), note=f"{series_code}/{sid}")
        return obs
