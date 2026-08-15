"""Provider registry — returns the active provider per data family.

Crypto rework: market data comes from Binance's public API (no key). 'Macro' is
replaced by two crypto series — the Fear & Greed index and the BTC market proxy.
"""

from __future__ import annotations

import logging

from app.config import Settings, get_settings
from app.providers.base import CallRecorder, NewsProvider, PriceProvider
from app.providers.context_onchain import ContextOnchainProvider
from app.providers.macro_crypto import CryptoMacroProvider
from app.providers.macro_market import FredMarketProvider
from app.providers.news_marketaux import MarketauxNewsProvider
from app.providers.prices_binance import BinancePriceProvider

logger = logging.getLogger("app.providers.registry")

# --- Macro sourcing plan (crypto + free context layers) ---------------------
# kind: "series" -> provider.get_series(code); "price" -> provider.get_price(code)
# Keyless layers are always planned; FRED-backed market series only when a key
# is configured (else they're surfaced as unavailable, honestly).
MACRO_SERIES_PLAN: list[tuple[str, str, str]] = [
    ("BTC", "crypto", "series"),        # Bitcoin close (USDT) — the market proxy
    ("FNG", "crypto", "series"),        # Fear & Greed index (0..100)
    ("STABLE", "onchain", "series"),    # Stablecoin supply (USD bn) — dry powder
    ("MVRV", "onchain", "series"),      # BTC market/realized cap — cycle valuation
]

# Series we knowingly cannot source without a key — surfaced honestly.
MACRO_SERIES_UNAVAILABLE: dict[str, str] = {
    "ETF_FLOW": "Spot BTC/ETH ETF net flows — needs a free SoSoValue API key "
                "(set SOSOVALUE_API_KEY).",
}

_MARKET_CODES = ["DXY", "GOLD", "US10Y", "SP500"]
if get_settings().fred_api_key:
    MACRO_SERIES_PLAN += [(c, "market", "series") for c in _MARKET_CODES]
else:
    for _c in _MARKET_CODES:
        MACRO_SERIES_UNAVAILABLE[_c] = (
            "Macro regime series — needs a free FRED API key (set FRED_API_KEY). "
            "https://fred.stlouisfed.org/docs/api/api_key.html"
        )

MACRO_SERIES_LABELS: dict[str, str] = {
    "BTC": "Bitcoin (USDT)",
    "FNG": "Fear & Greed",
    "STABLE": "Stablecoin supply (USD bn)",
    "MVRV": "BTC MVRV ratio",
    "DXY": "US Dollar Index (DXY)",
    "GOLD": "Gold (USD/oz)",
    "US10Y": "US 10y yield (%)",
    "SP500": "S&P 500",
    "ETF_FLOW": "Spot ETF net flows",
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
    """Macro providers: crypto (F&G + BTC) and free on-chain/liquidity context
    (DeFiLlama stablecoins + Coin Metrics MVRV), both keyless; plus FRED market
    data when a key is configured."""
    settings = settings or get_settings()
    providers: dict[str, object] = {
        "crypto": CryptoMacroProvider(call_recorder),
        "onchain": ContextOnchainProvider(call_recorder),
    }
    if settings.fred_api_key:
        providers["market"] = FredMarketProvider(settings.fred_api_key, call_recorder)
    return providers


def get_news_provider(
    call_recorder: CallRecorder | None = None,
    settings: Settings | None = None,
) -> NewsProvider | None:
    """Optional crypto news via Marketaux (needs key); None if unavailable."""
    settings = settings or get_settings()
    if settings.marketaux_api_key:
        return MarketauxNewsProvider(settings.marketaux_api_key, call_recorder)
    return None
