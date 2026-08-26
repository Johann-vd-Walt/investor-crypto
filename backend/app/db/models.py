"""SQLAlchemy 2.0 ORM models — the schema in PROJECT_SPEC.md §7.

Conventions (hard rules):
- Money is ``DECIMAL`` (``Numeric``), never float (Guardrail 2.2).
- JSE prices are stored in **cents (ZAc)** (Guardrail 2.3). Conversion to Rand
  happens only in the presentation layer.
- MySQL 8 target: unsigned ints, native ENUM/JSON, InnoDB, utf8mb4.
"""

from __future__ import annotations

import enum
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    CHAR,
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.mysql import (
    BIGINT,
    INTEGER,
    JSON,
    SMALLINT,
    TIMESTAMP,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base

# Reusable MySQL unsigned-int type aliases so FK columns match their PKs.
UInt = INTEGER(unsigned=True)
UBigInt = BIGINT(unsigned=True)

# Server-side timestamp defaults (MySQL).
_NOW = text("CURRENT_TIMESTAMP")
_NOW_ON_UPDATE = text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP")


# --- Enums (native MySQL ENUM) ---------------------------------------------


class SignalDirection(str, enum.Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


class SignalStatus(str, enum.Enum):
    OPEN = "OPEN"
    ACTED = "ACTED"
    EXPIRED = "EXPIRED"
    DISMISSED = "DISMISSED"


class TradeSide(str, enum.Enum):
    BUY = "BUY"
    SELL = "SELL"


class PaperTradeStatus(str, enum.Enum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"


# --- Reference data ---------------------------------------------------------


class Security(Base):
    __tablename__ = "securities"

    id: Mapped[int] = mapped_column(UInt, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(String(12), nullable=False, unique=True)
    isin: Mapped[str | None] = mapped_column(String(12), nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    sector: Mapped[str | None] = mapped_column(String(100), nullable=True)
    currency: Mapped[str] = mapped_column(
        String(8), nullable=False, server_default=text("'USDT'")
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("1")
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, nullable=False, server_default=_NOW
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, nullable=False, server_default=_NOW_ON_UPDATE
    )

    watchlist_entry: Mapped["Watchlist | None"] = relationship(
        back_populates="security", uselist=False
    )


class PriceBar(Base):
    """OHLCV daily bar. Prices in cents (ZAc)."""

    __tablename__ = "price_bars"

    security_id: Mapped[int] = mapped_column(
        UInt, ForeignKey("securities.id"), primary_key=True
    )
    timeframe: Mapped[str] = mapped_column(String(5), primary_key=True)
    bar_datetime: Mapped[datetime] = mapped_column(DateTime, primary_key=True)
    open: Mapped[Decimal] = mapped_column(Numeric(24, 10), nullable=False)
    high: Mapped[Decimal] = mapped_column(Numeric(24, 10), nullable=False)
    low: Mapped[Decimal] = mapped_column(Numeric(24, 10), nullable=False)
    close: Mapped[Decimal] = mapped_column(Numeric(24, 10), nullable=False)
    adj_close: Mapped[Decimal | None] = mapped_column(Numeric(24, 10), nullable=True)
    volume: Mapped[int | None] = mapped_column(UBigInt, nullable=True)
    source: Mapped[str] = mapped_column(String(40), nullable=False)
    is_delayed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("1")
    )
    ingested_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, nullable=False, server_default=_NOW
    )


class IndicatorValue(Base):
    """Cached computed indicator (tall/flexible). Recompute is cheap."""

    __tablename__ = "indicator_values"

    security_id: Mapped[int] = mapped_column(
        UInt, ForeignKey("securities.id"), primary_key=True
    )
    timeframe: Mapped[str] = mapped_column(String(5), primary_key=True)
    bar_datetime: Mapped[datetime] = mapped_column(DateTime, primary_key=True)
    indicator: Mapped[str] = mapped_column(String(40), primary_key=True)
    value: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    computed_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, nullable=False, server_default=_NOW
    )


class MacroSeries(Base):
    """Macro, commodity, FX and index series."""

    __tablename__ = "macro_series"

    series_code: Mapped[str] = mapped_column(String(30), primary_key=True)
    observation_date: Mapped[date] = mapped_column(Date, primary_key=True)
    value: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    unit: Mapped[str | None] = mapped_column(String(30), nullable=True)
    source: Mapped[str] = mapped_column(String(40), nullable=False)
    ingested_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, nullable=False, server_default=_NOW
    )


# --- News -------------------------------------------------------------------


class NewsArticle(Base):
    __tablename__ = "news_articles"
    __table_args__ = (Index("idx_news_published", "published_at"),)

    id: Mapped[int] = mapped_column(UBigInt, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(80), nullable=False)
    url: Mapped[str] = mapped_column(String(768), nullable=False)
    url_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False, unique=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    snippet: Mapped[str | None] = mapped_column(Text, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    language: Mapped[str | None] = mapped_column(String(8), nullable=True)
    raw: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, nullable=False, server_default=_NOW
    )

    sentiments: Mapped[list["NewsSentiment"]] = relationship(
        back_populates="article", cascade="all, delete-orphan"
    )


class NewsSentiment(Base):
    __tablename__ = "news_sentiment"
    __table_args__ = (Index("idx_sent_sec", "security_id", "created_at"),)

    id: Mapped[int] = mapped_column(UBigInt, primary_key=True, autoincrement=True)
    article_id: Mapped[int] = mapped_column(
        UBigInt, ForeignKey("news_articles.id", ondelete="CASCADE"), nullable=False
    )
    security_id: Mapped[int | None] = mapped_column(
        UInt, ForeignKey("securities.id"), nullable=True
    )
    entity_symbol: Mapped[str | None] = mapped_column(String(40), nullable=True)
    sentiment: Mapped[Decimal | None] = mapped_column(Numeric(6, 4), nullable=True)
    relevance: Mapped[Decimal | None] = mapped_column(Numeric(6, 4), nullable=True)
    model: Mapped[str | None] = mapped_column(String(40), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, nullable=False, server_default=_NOW
    )

    article: Mapped["NewsArticle"] = relationship(back_populates="sentiments")


# --- Signals ----------------------------------------------------------------


class SensAnnouncement(Base):
    """JSE SENS / company announcements (Phase D), deduped by url hash.

    Sourced from a configurable RSS feed (SENS_RSS_URL). ``security_id`` is set
    when the headline maps to a known security, else NULL (general/unmatched).
    """

    __tablename__ = "sens_announcements"
    __table_args__ = (Index("idx_sens_published", "published_at"),)

    id: Mapped[int] = mapped_column(UBigInt, primary_key=True, autoincrement=True)
    security_id: Mapped[int | None] = mapped_column(
        UInt, ForeignKey("securities.id"), nullable=True
    )
    source: Mapped[str] = mapped_column(String(80), nullable=False)
    url: Mapped[str] = mapped_column(String(768), nullable=False)
    url_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False, unique=True)
    headline: Mapped[str] = mapped_column(String(512), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str | None] = mapped_column(String(80), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    raw: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, nullable=False, server_default=_NOW
    )


class Signal(Base):
    __tablename__ = "signals"
    __table_args__ = (
        Index("idx_sig_gen", "generated_at"),
        Index("idx_sig_sec", "security_id", "generated_at"),
    )

    id: Mapped[int] = mapped_column(UBigInt, primary_key=True, autoincrement=True)
    security_id: Mapped[int] = mapped_column(
        UInt, ForeignKey("securities.id"), nullable=False
    )
    generated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    horizon_days: Mapped[int] = mapped_column(
        SMALLINT, nullable=False, server_default=text("10")
    )
    direction: Mapped[SignalDirection] = mapped_column(
        Enum(SignalDirection, native_enum=True), nullable=False
    )
    score: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(6, 4), nullable=True)
    technical_score: Mapped[Decimal | None] = mapped_column(Numeric(6, 4), nullable=True)
    macro_score: Mapped[Decimal | None] = mapped_column(Numeric(6, 4), nullable=True)
    sentiment_score: Mapped[Decimal | None] = mapped_column(Numeric(6, 4), nullable=True)
    suggested_entry: Mapped[Decimal | None] = mapped_column(Numeric(24, 10), nullable=True)
    suggested_stop: Mapped[Decimal | None] = mapped_column(Numeric(24, 10), nullable=True)
    # Fractional — crypto positions are not whole units.
    suggested_size: Mapped[Decimal | None] = mapped_column(Numeric(24, 10), nullable=True)
    rationale: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[SignalStatus] = mapped_column(
        Enum(SignalStatus, native_enum=True),
        nullable=False,
        server_default=text("'OPEN'"),
    )


# --- Watchlist / trades -----------------------------------------------------


class Watchlist(Base):
    __tablename__ = "watchlist"

    id: Mapped[int] = mapped_column(UInt, primary_key=True, autoincrement=True)
    security_id: Mapped[int] = mapped_column(
        UInt,
        ForeignKey("securities.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    added_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, nullable=False, server_default=_NOW
    )
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)

    security: Mapped["Security"] = relationship(back_populates="watchlist_entry")


class Trade(Base):
    """Real trades you actually placed (manual entry). Doubles as tax record."""

    __tablename__ = "trades"

    id: Mapped[int] = mapped_column(UBigInt, primary_key=True, autoincrement=True)
    security_id: Mapped[int] = mapped_column(
        UInt, ForeignKey("securities.id"), nullable=False
    )
    side: Mapped[TradeSide] = mapped_column(
        Enum(TradeSide, native_enum=True), nullable=False
    )
    quantity: Mapped[Decimal] = mapped_column(Numeric(24, 10), nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(24, 10), nullable=False)
    fees: Mapped[Decimal] = mapped_column(
        Numeric(24, 10), nullable=False, server_default=text("0")
    )
    trade_datetime: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    linked_signal_id: Mapped[int | None] = mapped_column(
        UBigInt, ForeignKey("signals.id"), nullable=True
    )
    rationale: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, nullable=False, server_default=_NOW
    )


class PaperTrade(Base):
    """Simulated trades so the engine can measure itself before real money."""

    __tablename__ = "paper_trades"

    id: Mapped[int] = mapped_column(UBigInt, primary_key=True, autoincrement=True)
    signal_id: Mapped[int | None] = mapped_column(
        UBigInt, ForeignKey("signals.id"), nullable=True
    )
    security_id: Mapped[int] = mapped_column(
        UInt, ForeignKey("securities.id"), nullable=False
    )
    entry_datetime: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    entry_price: Mapped[Decimal] = mapped_column(Numeric(24, 10), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(24, 10), nullable=False)
    stop_price: Mapped[Decimal | None] = mapped_column(Numeric(24, 10), nullable=True)
    exit_datetime: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    exit_price: Mapped[Decimal | None] = mapped_column(Numeric(24, 10), nullable=True)
    pnl: Mapped[Decimal | None] = mapped_column(Numeric(24, 10), nullable=True)
    status: Mapped[PaperTradeStatus] = mapped_column(
        Enum(PaperTradeStatus, native_enum=True),
        nullable=False,
        server_default=text("'OPEN'"),
    )


class AppConfig(Base):
    """Single-row store of runtime-tunable settings overrides (Phase 8).

    Env/.env provides defaults; the Settings page writes overrides here, which
    ``services/settings.get_effective_settings`` layers on top. Only whitelisted
    tunable fields are ever stored.
    """

    __tablename__ = "app_config"

    id: Mapped[int] = mapped_column(UInt, primary_key=True, autoincrement=True)
    overrides: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, nullable=False, server_default=_NOW_ON_UPDATE
    )


class DerivativeMetric(Base):
    """Time series of Binance USDⓈ-M futures positioning metrics (Tier 1).

    Tall/flexible like ``indicator_values``: one row per (security, metric,
    timestamp). Binance only retains ~30 days of most of these, so we poll and
    persist to build our own history for percentile-based flags. Free data.

    ``metric`` values: 'funding' (funding rate), 'open_interest' (USD value),
    'long_short_pos' (top-trader position ratio), 'taker_ratio' (taker buy/sell).
    Not wiped by the seeder — re-fetchable but cheap to keep.
    """

    __tablename__ = "derivative_metrics"

    security_id: Mapped[int] = mapped_column(
        UInt, ForeignKey("securities.id", ondelete="CASCADE"), primary_key=True
    )
    metric: Mapped[str] = mapped_column(String(24), primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime, primary_key=True)
    value: Mapped[Decimal] = mapped_column(Numeric(30, 10), nullable=False)
    ingested_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, nullable=False, server_default=_NOW
    )


class BotState(Base):
    """Singleton (id=1) state for the real-time PAPER trading bot.

    The bot simulates a portfolio against LIVE prices — no real orders, no
    exchange keys, no real money. ``cash`` + open ``BotPosition`` mark-to-market
    = equity. Not wiped by the seeder.
    """

    __tablename__ = "bot_state"

    id: Mapped[int] = mapped_column(UInt, primary_key=True)  # singleton, always 1
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("0"))
    tick_seconds: Mapped[int] = mapped_column(INTEGER, nullable=False, server_default=text("60"))
    initial_cash: Mapped[Decimal] = mapped_column(Numeric(24, 10), nullable=False)
    cash: Mapped[Decimal] = mapped_column(Numeric(24, 10), nullable=False)
    realized_pnl: Mapped[Decimal] = mapped_column(
        Numeric(24, 10), nullable=False, server_default=text("0")
    )
    last_equity: Mapped[Decimal | None] = mapped_column(Numeric(24, 10), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_tick_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, nullable=False, server_default=_NOW_ON_UPDATE
    )


class BotPosition(Base):
    """One simulated position held by the paper bot (long-only)."""

    __tablename__ = "bot_positions"

    id: Mapped[int] = mapped_column(UBigInt, primary_key=True, autoincrement=True)
    security_id: Mapped[int] = mapped_column(UInt, ForeignKey("securities.id"), nullable=False)
    signal_id: Mapped[int | None] = mapped_column(UBigInt, ForeignKey("signals.id"), nullable=True)
    entry_datetime: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    entry_price: Mapped[Decimal] = mapped_column(Numeric(24, 10), nullable=False)
    # Fractional — crypto positions are not whole units.
    quantity: Mapped[Decimal] = mapped_column(Numeric(24, 10), nullable=False)
    stop_price: Mapped[Decimal | None] = mapped_column(Numeric(24, 10), nullable=True)
    horizon_days: Mapped[int] = mapped_column(SMALLINT, nullable=False, server_default=text("10"))
    cost_basis: Mapped[Decimal] = mapped_column(Numeric(24, 10), nullable=False)  # cash spent incl fees
    status: Mapped[str] = mapped_column(String(8), nullable=False, server_default=text("'OPEN'"))
    exit_datetime: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    exit_price: Mapped[Decimal | None] = mapped_column(Numeric(24, 10), nullable=True)
    pnl: Mapped[Decimal | None] = mapped_column(Numeric(24, 10), nullable=True)  # realized, net
    exit_reason: Mapped[str | None] = mapped_column(String(16), nullable=True)


class BotEvent(Base):
    """Activity log for the paper bot (what it did each tick)."""

    __tablename__ = "bot_events"
    __table_args__ = (Index("idx_botevt_at", "created_at"),)

    id: Mapped[int] = mapped_column(UBigInt, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP, nullable=False, server_default=_NOW)
    kind: Mapped[str] = mapped_column(String(12), nullable=False)  # open|close|skip|start|stop|info|error
    ticker: Mapped[str | None] = mapped_column(String(12), nullable=True)
    detail: Mapped[str] = mapped_column(String(400), nullable=False)
    equity: Mapped[Decimal | None] = mapped_column(Numeric(24, 10), nullable=True)


class BotEquity(Base):
    """Equity time series for the paper bot's live curve."""

    __tablename__ = "bot_equity"
    __table_args__ = (Index("idx_boteq_ts", "ts"),)

    id: Mapped[int] = mapped_column(UBigInt, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    equity: Mapped[Decimal] = mapped_column(Numeric(24, 10), nullable=False)
    cash: Mapped[Decimal] = mapped_column(Numeric(24, 10), nullable=False)


class AuthEvent(Base):
    """Security log: every attempt to pass the app's TOTP login gate.

    Recorded per attempt so the owner can see if anyone is probing the login.
    Deliberately NOT listed in the seeder's wipe set — security history should
    survive a re-seed.
    """

    __tablename__ = "auth_events"
    __table_args__ = (Index("idx_authevt_at", "created_at"),)

    id: Mapped[int] = mapped_column(UBigInt, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, nullable=False, server_default=_NOW
    )
    # "success" | "failed" | "locked" (rate-limited).
    event: Mapped[str] = mapped_column(String(20), nullable=False)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(255), nullable=True)


class ProviderCall(Base):
    """Rate-limit and health tracking for every external call (Guardrail 2.6)."""

    __tablename__ = "provider_calls"
    __table_args__ = (Index("idx_prov", "provider", "called_at"),)

    id: Mapped[int] = mapped_column(UBigInt, primary_key=True, autoincrement=True)
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    endpoint: Mapped[str | None] = mapped_column(String(255), nullable=True)
    called_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, nullable=False, server_default=_NOW
    )
    status_code: Mapped[int | None] = mapped_column(INTEGER, nullable=True)
    rows_returned: Mapped[int | None] = mapped_column(INTEGER, nullable=True)
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)
