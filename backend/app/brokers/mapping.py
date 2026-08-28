"""Map the app's Binance USDT tickers to Luno trading pairs.

Only the coins Luno actually lists against USDT are tradeable there. Bitcoin is
``XBT`` on Luno (not BTC). Everything else that isn't a live Luno USDT pair is
deliberately un-tradeable (the bot skips it with a clear reason) — verified
against https://api.luno.com/api/exchange/1/markets.
"""

from __future__ import annotations

# app base symbol -> Luno base symbol (only the USDT-supported ones)
_LUNO_BASE: dict[str, str] = {
    "BTC": "XBT",
    "ETH": "ETH",
    "BNB": "BNB",
    "SOL": "SOL",
    "XRP": "XRP",
    "ADA": "ADA",
    "DOGE": "DOGE",
    "LINK": "LINK",
    "TRX": "TRX",
    "XLM": "XLM",
    "BCH": "BCH",
}

# Coins the app knows but Luno can't trade in USDT (surfaced honestly).
NOT_ON_LUNO_USDT = ["AVAX", "DOT", "LTC", "ATOM", "UNI", "ETC", "FIL", "NEAR", "APT", "ARB", "OP"]


def app_base(ticker: str) -> str:
    """'BTCUSDT' -> 'BTC'."""
    t = ticker.strip().upper()
    return t[:-4] if t.endswith("USDT") else t


def to_luno_pair(ticker: str) -> str | None:
    """App ticker (e.g. 'BTCUSDT') -> Luno pair (e.g. 'XBTUSDT'), or None if the
    coin isn't tradeable on Luno in USDT."""
    base = app_base(ticker)
    luno_base = _LUNO_BASE.get(base)
    return f"{luno_base}USDT" if luno_base else None


def is_tradeable(ticker: str) -> bool:
    return to_luno_pair(ticker) is not None
