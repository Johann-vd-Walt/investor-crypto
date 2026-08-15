"""OKX public copy-trading provider (Tier 4 — free, no key).

Reads OKX's public lead-trader rankings and their CURRENT positions to build a
crowd-consensus ("what are the top traders positioned in"). Read-only; the app
never copies or trades. These are the WEAKEST signals we surface — survivorship
bias, latency, and manipulation are rife — so everything is framed as
low-confidence context. Public endpoints need no API key.
"""

from __future__ import annotations

import logging

import httpx

from app.providers.base import BaseProvider

logger = logging.getLogger("app.providers.okx")

_BASE = "https://www.okx.com"
_LEADERS = "/api/v5/copytrading/public-lead-traders"
_POSITIONS = "/api/v5/copytrading/public-current-subpositions"
_HEADERS = {"User-Agent": "Mozilla/5.0"}


class OkxCopyTradingProvider(BaseProvider):
    @property
    def name(self) -> str:
        return "okx_copytrading"

    def _get(self, path: str, params: dict) -> list:
        url = f"{_BASE}{path}"
        try:
            resp = httpx.get(url, params=params, headers=_HEADERS, timeout=20.0)
        except httpx.HTTPError as exc:
            self._record(endpoint=url, status_code=None, rows_returned=None, note=str(exc))
            raise
        if resp.status_code != 200:
            self._record(endpoint=url, status_code=resp.status_code, rows_returned=None, note=resp.text[:120])
            resp.raise_for_status()
        body = resp.json()
        if body.get("code") != "0":
            self._record(endpoint=url, status_code=resp.status_code, rows_returned=None, note=f"okx code {body.get('code')}: {body.get('msg')}")
            return []
        data = body.get("data") or []
        self._record(endpoint=url, status_code=200, rows_returned=len(data), note=path)
        return data

    def get_lead_traders(self, *, inst_type: str = "SWAP", limit: int = 12) -> list[dict]:
        """Top lead traders (public rankings). Returns rank dicts."""
        data = self._get(_LEADERS, {"instType": inst_type, "sortType": "pnl_ratio", "limit": limit})
        if not data or "ranks" not in data[0]:
            return []
        return data[0]["ranks"][:limit]

    def get_positions(self, unique_code: str, *, inst_type: str = "SWAP") -> list[dict]:
        """A lead trader's current open positions (subpositions)."""
        return self._get(_POSITIONS, {"instType": inst_type, "uniqueCode": unique_code})
