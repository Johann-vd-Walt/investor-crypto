"""Luno exchange REST client for LIVE trading (real money).

Verified against Luno's official SDK + live API. HTTP Basic auth (key id / secret).
Market BUY is sized by counter (USDT) amount; market SELL by base (coin) amount.
Luno has NO sandbox — every authenticated call is production. Keys come from the
environment only; a blank key means live trading is impossible (by design).

This client only TALKS to Luno. Whether/when it's used for real orders is gated
by the bot's mode + dry-run + guardrails, never by this module alone.
"""

from __future__ import annotations

import logging
import time
from decimal import Decimal

import httpx

logger = logging.getLogger("app.brokers.luno")

_BASE = "https://api.luno.com"


class LunoError(RuntimeError):
    pass


class LunoBroker:
    def __init__(self, key_id: str, key_secret: str, *, base_url: str = _BASE) -> None:
        self._key_id = key_id
        self._client = httpx.Client(base_url=base_url, auth=(key_id, key_secret), timeout=30.0)
        self._rules: dict[str, dict] | None = None

    @property
    def configured(self) -> bool:
        return bool(self._key_id)

    # --- low-level with light 429/5xx backoff ---
    def _req(self, method: str, path: str, **kw) -> dict:
        last = None
        for attempt in range(4):
            try:
                resp = self._client.request(method, path, **kw)
            except httpx.HTTPError as exc:
                last = exc
                time.sleep(0.5 * (attempt + 1))
                continue
            if resp.status_code == 429 or resp.status_code >= 500:
                time.sleep(0.7 * (attempt + 1))
                last = LunoError(f"{resp.status_code}: {resp.text[:160]}")
                continue
            if resp.status_code >= 400:
                raise LunoError(f"Luno {resp.status_code}: {resp.text[:200]}")
            return resp.json()
        raise LunoError(f"Luno request failed after retries: {last}")

    # --- read-only ---
    def markets(self) -> dict[str, dict]:
        """Cache and return per-pair trading rules keyed by market_id."""
        if self._rules is None:
            data = self._req("GET", "/api/exchange/1/markets")
            self._rules = {m["market_id"]: m for m in data.get("markets", [])}
        return self._rules

    def rule(self, pair: str) -> dict | None:
        return self.markets().get(pair)

    def balances(self) -> dict[str, dict]:
        """{asset: {balance, reserved, available}} (available = balance - reserved)."""
        rows = self._req("GET", "/api/1/balance").get("balance", [])
        out: dict[str, dict] = {}
        for r in rows:
            bal = Decimal(str(r.get("balance", "0")))
            res = Decimal(str(r.get("reserved", "0")))
            out[r["asset"]] = {"balance": bal, "reserved": res, "available": bal - res,
                               "account_id": r.get("account_id")}
        return out

    def available(self, asset: str) -> Decimal:
        return self.balances().get(asset, {}).get("available", Decimal(0))

    def ticker(self, pair: str) -> Decimal | None:
        try:
            d = self._req("GET", "/api/1/ticker", params={"pair": pair})
            return Decimal(str(d["last_trade"])) if d.get("last_trade") else None
        except (LunoError, KeyError):
            return None

    def tickers(self) -> dict[str, Decimal]:
        """All markets' last-trade prices in one call: {pair: price}."""
        out: dict[str, Decimal] = {}
        try:
            for t in self._req("GET", "/api/1/tickers").get("tickers", []):
                lt = t.get("last_trade")
                if t.get("pair") and lt:
                    try:
                        out[t["pair"]] = Decimal(str(lt))
                    except Exception:  # noqa: BLE001
                        continue
        except LunoError as exc:
            logger.warning("luno tickers failed: %s", exc)
        return out

    def fee_info(self, pair: str) -> dict:
        return self._req("GET", "/api/1/fee_info", params={"pair": pair})

    # --- orders (REAL money) ---
    def market_buy(self, pair: str, counter_volume: Decimal, client_order_id: str) -> str:
        """BUY: spend ``counter_volume`` USDT at market. Returns order_id."""
        d = self._req("POST", "/api/1/marketorder", data={
            "pair": pair, "type": "BUY",
            "counter_volume": str(counter_volume),
            "client_order_id": client_order_id,
        })
        return d["order_id"]

    def market_sell(self, pair: str, base_volume: Decimal, client_order_id: str) -> str:
        """SELL: sell ``base_volume`` coins at market. Returns order_id."""
        d = self._req("POST", "/api/1/marketorder", data={
            "pair": pair, "type": "SELL",
            "base_volume": str(base_volume),
            "client_order_id": client_order_id,
        })
        return d["order_id"]

    def get_order(self, order_id: str) -> dict:
        """Order state for reconciliation (v2 endpoint: status/base/counter/fees)."""
        return self._req("GET", f"/api/exchange/2/orders/{order_id}")

    def cancel(self, order_id: str) -> bool:
        d = self._req("POST", "/api/1/stoporder", data={"order_id": order_id})
        return bool(d.get("success"))

    def close(self) -> None:
        self._client.close()
