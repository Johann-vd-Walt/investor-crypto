"""Provider registry — returns the active provider per data family.

Crypto rework: market data comes from Binance's public API (no key). 'Macro' is
replaced by two crypto series — the Fear & Greed index and the BTC market proxy.
"""

from __future__ import annotations

import logging

from app.config import Settings, get_settings
from app.providers.base import CallRecorder, NewsProvider, PriceProvider
from app.providers.macro_crypto import CryptoMacroProvider
from app.providers.news_marketaux import MarketauxNewsProvider
from app.providers.prices_binance import BinancePriceProvider

logger = logging.getLogger("app.providers.registry")

# --- Macro sourcing plan (crypto) -------------------------------------------
# kind: "series" -> provider.get_series(code); "price" -> provider.get_price(code)
MACRO_SERIES_PLAN: list[tuple[str, str, str]] = [
    ("BTC", "crypto", "series"),   # Bitcoin close (USDT) — the market proxy
    ("FNG", "crypto", "series"),   # Fear & Greed index (0..100)
]

MACRO_SERIES_UNAVAILABLE: dict[str, str] = {}

MACRO_SERIES_LABELS: dict[str, str] = {
    "BTC": "Bitcoin (USDT)",
    "FNG": "Fear & Greed",
}


def get_price_provider(
    call_recorder: CallRecorder | None = None,
    settings: Settings | None = None,
) -> PriceProvider:
    """Return the active price provider (Binance public API — no key)."""
    settings = settings or get_settings()
    logger.info("Using Binance as the active price provider.")
    return BinancePriceProvider(call_recorder, base_url=settings.binance_base_url)


def get_macro_providers(
    call_recorder: CallRecorder | None = None,
    settings: Settings | None = None,
) -> dict[str, object]:
    """Crypto 'macro' provider (Fear & Greed + BTC market series) — keyless."""
    return {"crypto": CryptoMacroProvider(call_recorder)}


def get_news_provider(
    call_recorder: CallRecorder | None = None,
    settings: Settings | None = None,
) -> NewsProvider | None:
    """Optional crypto news via Marketaux (needs key); None if unavailable."""
    settings = settings or get_settings()
    if settings.marketaux_api_key:
        return MarketauxNewsProvider(settings.marketaux_api_key, call_recorder)
    return None
