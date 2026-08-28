"""Application configuration.

Loads settings from environment / ``.env`` via Pydantic Settings.

Guardrail (Section 6): the app MUST start cleanly with any provider key
missing. A missing key disables that provider and logs a warning; it never
crashes the app.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from functools import lru_cache

from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger("app.config")

# Provider keys and the data family each one powers. Used to log which
# providers are active vs disabled at startup.
PROVIDER_KEYS: dict[str, str] = {
    "EODHD_API_KEY": "JSE prices / fundamentals",
    "ALPHAVANTAGE_API_KEY": "FX / macro / commodities fallback",
    "MARKETAUX_API_KEY": "news + sentiment",
    "OILPRICE_API_KEY": "commodities (energy)",
}


class Settings(BaseSettings):
    """Typed application settings, loaded from ``.env``.

    Every field has a safe default so the app boots even with an empty
    environment. Provider keys default to empty string = disabled.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Database
    database_url: str = Field(
        default="mysql+pymysql://jse_user:changeme@localhost:3306/jse_swingtrader",
        alias="DATABASE_URL",
    )

    # Provider keys (blank = disabled). Crypto market data (Binance) needs NO key;
    # these remain for optional news/sentiment and are safe to leave blank.
    eodhd_api_key: str = Field(default="", alias="EODHD_API_KEY")
    alphavantage_api_key: str = Field(default="", alias="ALPHAVANTAGE_API_KEY")
    marketaux_api_key: str = Field(default="", alias="MARKETAUX_API_KEY")
    oilprice_api_key: str = Field(default="", alias="OILPRICE_API_KEY")
    # Tier 2 context sources that need a FREE key (blank = that layer disabled):
    #   FRED (macro regime: DXY/gold/yields/S&P) — https://fred.stlouisfed.org/docs/api/api_key.html
    #   SoSoValue (spot BTC/ETH ETF net flows)   — https://sosovalue.com/developer
    fred_api_key: str = Field(default="", alias="FRED_API_KEY")
    sosovalue_api_key: str = Field(default="", alias="SOSOVALUE_API_KEY")
    # Luno exchange keys for LIVE trading (blank = live trading impossible).
    # Real money — only set these when you intend to trade for real.
    luno_api_key_id: str = Field(default="", alias="LUNO_API_KEY_ID")
    luno_api_key_secret: str = Field(default="", alias="LUNO_API_KEY_SECRET")

    # App
    app_env: str = Field(default="development", alias="APP_ENV")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    # --- Crypto market data (Binance public API, no key) ---
    # Active price provider: "binance" (default, no key). Kept pluggable.
    price_provider: str = Field(default="binance", alias="PRICE_PROVIDER")
    binance_base_url: str = Field(
        default="https://data-api.binance.vision", alias="BINANCE_BASE_URL"
    )
    # Binance USDⓈ-M FUTURES host (funding/OI/positioning data). Different host
    # from spot; may be geo-restricted on some servers — the app degrades
    # gracefully (derivatives simply stay empty) if it's unreachable.
    binance_futures_base_url: str = Field(
        default="https://fapi.binance.com", alias="BINANCE_FUTURES_BASE_URL"
    )
    # Quote currency of the traded pairs (prices are stored/returned in this).
    quote_currency: str = Field(default="USDT", alias="QUOTE_CURRENCY")
    # Crypto Fear & Greed index (alternative.me, free, no key).
    fear_greed_url: str = Field(default="https://api.alternative.me/fng/", alias="FEAR_GREED_URL")

    # Crypto news RSS (optional; free feeds may be empty). Blank disables.
    sens_rss_url: str = Field(
        default="https://cointelegraph.com/rss",
        alias="SENS_RSS_URL",
    )

    # Signal engine weights (must sum to 1.0)
    weight_technical: float = Field(default=0.5, alias="WEIGHT_TECHNICAL")
    weight_macro: float = Field(default=0.2, alias="WEIGHT_MACRO")
    weight_sentiment: float = Field(default=0.3, alias="WEIGHT_SENTIMENT")
    default_horizon_days: int = Field(default=10, alias="DEFAULT_HORIZON_DAYS")

    # Fused-score thresholds for direction (score in -1..1).
    buy_threshold: float = Field(default=0.3, alias="BUY_THRESHOLD")
    sell_threshold: float = Field(default=-0.3, alias="SELL_THRESHOLD")

    # Position sizing / stops. account_size is in the quote currency (USDT).
    account_size: Decimal = Field(default=Decimal("10000"), alias="ACCOUNT_SIZE")  # USDT
    risk_per_trade_pct: Decimal = Field(default=Decimal("1.0"), alias="RISK_PER_TRADE_PCT")
    atr_stop_multiple: Decimal = Field(default=Decimal("2.0"), alias="ATR_STOP_MULTIPLE")

    # Realistic paper-trade costs (per side, % of notional). Honesty req: a
    # cost-free simulation is misleading. Crypto exchange taker fees ~0.1%/side
    # (Binance/VALR); slippage ~0.1% approximates spread/impact.
    brokerage_pct: Decimal = Field(default=Decimal("0.1"), alias="BROKERAGE_PCT")
    slippage_pct: Decimal = Field(default=Decimal("0.1"), alias="SLIPPAGE_PCT")
    # No transfer tax on crypto trades (unlike JSE STT). Kept at 0 for the shared
    # cost model; SA still taxes crypto GAINS — see the journal/tax page.
    stt_pct: Decimal = Field(default=Decimal("0"), alias="STT_PCT")

    # --- Liquidity & portfolio risk controls ---
    # Minimum average daily traded value (in the QUOTE currency, e.g. USDT) for a
    # market to be tradable. Field name kept for compatibility.
    min_liquidity_zar: Decimal = Field(default=Decimal("5000000"), alias="MIN_LIQUIDITY_ZAR")
    liquidity_lookback_days: int = Field(default=20, alias="LIQUIDITY_LOOKBACK_DAYS")
    # Cross-sectional momentum layer weight (0 = disabled; fusion renormalises).
    weight_momentum: float = Field(default=0.0, alias="WEIGHT_MOMENTUM")
    momentum_lookback_days: int = Field(default=90, alias="MOMENTUM_LOOKBACK_DAYS")
    momentum_skip_days: int = Field(default=5, alias="MOMENTUM_SKIP_DAYS")
    # Portfolio caps applied when opening paper trades.
    max_open_positions: int = Field(default=10, alias="MAX_OPEN_POSITIONS")
    max_positions_per_sector: int = Field(default=3, alias="MAX_POSITIONS_PER_SECTOR")
    # Trailing stop as % below the highest close since entry (0 = disabled).
    trailing_stop_pct: Decimal = Field(default=Decimal("0"), alias="TRAILING_STOP_PCT")

    # --- Auth: global TOTP gate (Google Authenticator) ---
    # Base32 secret. BLANK = auth disabled (no login required — safe default so
    # you can't lock yourself out before enrolling). Run `python -m app.auth_setup`
    # to generate one and print a QR, then set it here.
    totp_secret: str = Field(default="", alias="TOTP_SECRET")
    # Signing key for session tokens. Blank -> derived from TOTP_SECRET (stable).
    auth_secret_key: str = Field(default="", alias="AUTH_SECRET_KEY")
    session_ttl_hours: int = Field(default=12, alias="SESSION_TTL_HOURS")
    totp_issuer: str = Field(default="Crypto Swing-Trader", alias="TOTP_ISSUER")
    totp_account: str = Field(default="owner", alias="TOTP_ACCOUNT")

    # CORS
    frontend_origin: str = Field(
        default="http://localhost:5173", alias="FRONTEND_ORIGIN"
    )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def enabled_providers(self) -> dict[str, bool]:
        """Map of provider-key name -> whether it is configured (non-blank)."""
        return {
            "EODHD_API_KEY": bool(self.eodhd_api_key),
            "ALPHAVANTAGE_API_KEY": bool(self.alphavantage_api_key),
            "MARKETAUX_API_KEY": bool(self.marketaux_api_key),
            "OILPRICE_API_KEY": bool(self.oilprice_api_key),
        }

    @property
    def weight_sum(self) -> float:
        return self.weight_technical + self.weight_macro + self.weight_sentiment


def _log_startup_diagnostics(settings: Settings) -> None:
    """Warn (never crash) about missing provider keys and bad weights."""
    for key, family in PROVIDER_KEYS.items():
        if settings.enabled_providers.get(key):
            logger.info("Provider key %s present — %s enabled.", key, family)
        else:
            logger.warning(
                "Provider key %s is missing — %s disabled.", key, family
            )

    if abs(settings.weight_sum - 1.0) > 1e-6:
        logger.warning(
            "Signal weights sum to %.4f, not 1.0 "
            "(technical=%.2f, macro=%.2f, sentiment=%.2f). "
            "Fusion will normalise, but please fix .env.",
            settings.weight_sum,
            settings.weight_technical,
            settings.weight_macro,
            settings.weight_sentiment,
        )


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance and log startup diagnostics once."""
    settings = Settings()
    _log_startup_diagnostics(settings)
    return settings
