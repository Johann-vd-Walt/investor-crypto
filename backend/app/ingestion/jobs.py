"""Ingestion jobs (Section 9).

All jobs: log to ``provider_calls``, dedupe on write, mark ``is_delayed``, back
off on HTTP 429, and never crash on a single failure.

Phase 2 implements ``ingest_daily_prices``. Later phases add macro/news/etc.
"""

from __future__ import annotations

import logging
import re
from collections import Counter
from datetime import date, datetime, timedelta

import pandas as pd
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import PriceBar, SignalDirection
from app.db.session import SessionLocal
from app.ingestion.backoff import call_with_backoff
from app.providers.base import Bar, PriceProvider, ProviderCallInfo
from app.providers.registry import (
    MACRO_SERIES_PLAN,
    get_macro_providers,
    get_news_provider,
    get_price_provider,
)
from app.repositories import derivatives as deriv_repo
from app.repositories import indicators as indicators_repo
from app.repositories import macro as macro_repo
from app.repositories import news as news_repo
from app.repositories import paper as paper_repo
from app.repositories import prices as prices_repo
from app.repositories import provider_calls as calls_repo
from app.repositories import securities as securities_repo
from app.repositories import sens as sens_repo
from app.repositories import signals as signals_repo
from app.repositories import watchlist as watchlist_repo
from app.providers.sens_rss import SensRssProvider
from app.services import settings as settings_service
from app.signals import indicators as indicators_calc
from app.signals import engine as signal_engine
from app.signals import macro_regime, momentum, paper, performance

logger = logging.getLogger("app.ingestion")


def _fetch_with_backoff(
    provider: PriceProvider, ticker: str, start: date, end: date
) -> list[Bar]:
    """Call the provider, backing off on HTTP 429 (Guardrail 2.6)."""
    return call_with_backoff(
        lambda: provider.get_daily_bars(ticker, start, end), label=ticker
    )


def ingest_daily_prices(
    tickers: list[str] | None = None,
    *,
    lookback_days: int = 365,
    db: Session | None = None,
) -> dict:
    """Pull EOD daily bars for the given tickers (default: the watchlist).

    Returns a summary dict. Never raises for a single security's failure — it
    records the failure and moves on (Guardrail 2.7).
    """
    owns_session = db is None
    db = db or SessionLocal()
    recorder = lambda info: calls_repo.record(db, info)  # noqa: E731

    provider = get_price_provider(call_recorder=recorder)
    end = date.today()
    start = end - timedelta(days=lookback_days)

    # Resolve target securities.
    if tickers:
        targets = [
            s for t in tickers if (s := securities_repo.get_by_ticker(db, t)) is not None
        ]
        unknown = [t for t in tickers if securities_repo.get_by_ticker(db, t) is None]
        for t in unknown:
            logger.warning("ingest_daily_prices: unknown ticker %s (skipped)", t)
    else:
        targets = [e.security for e in watchlist_repo.list_entries(db)]

    summary = {
        "provider": provider.name,
        "requested": len(targets),
        "succeeded": 0,
        "failed": 0,
        "rows_written": 0,
        "errors": {},
    }

    for sec in targets:
        try:
            bars = _fetch_with_backoff(provider, sec.ticker, start, end)
            written = prices_repo.upsert_bars(
                db,
                security_id=sec.id,
                timeframe="1d",
                source=provider.name,
                bars=bars,
            )
            db.commit()
            summary["succeeded"] += 1
            summary["rows_written"] += written
            logger.info("Ingested %d bars for %s", written, sec.ticker)
        except Exception as exc:  # noqa: BLE001 — isolate per-security failures
            db.rollback()
            # Still record that we tried and failed.
            try:
                calls_repo.record(
                    db,
                    ProviderCallInfo(
                        provider=provider.name,
                        endpoint=None,
                        status_code=None,
                        rows_returned=None,
                        note=f"ingest failed for {sec.ticker}: {exc}",
                    ),
                )
                db.commit()
            except Exception:  # noqa: BLE001
                db.rollback()
            summary["failed"] += 1
            summary["errors"][sec.ticker] = str(exc)
            logger.warning("Failed to ingest %s: %s", sec.ticker, exc)

    if owns_session:
        db.close()
    return summary


def ingest_macro(db: Session | None = None) -> dict:
    """Ingest macro/commodity/FX/index series per the registry plan (§9).

    Each series is isolated: a failure (throttle, network, missing provider)
    is recorded and skipped without aborting the others (Guardrail 2.7).
    """
    owns_session = db is None
    db = db or SessionLocal()
    recorder = lambda info: calls_repo.record(db, info)  # noqa: E731
    providers = get_macro_providers(call_recorder=recorder)

    summary = {"succeeded": 0, "failed": 0, "skipped": 0, "rows_written": 0, "errors": {}}

    for series_code, provider_name, kind in MACRO_SERIES_PLAN:
        provider = providers.get(provider_name)
        if provider is None:
            summary["skipped"] += 1
            summary["errors"][series_code] = f"provider '{provider_name}' unavailable"
            logger.warning("Skipping %s — provider %s unavailable.", series_code, provider_name)
            continue
        try:
            if kind == "price":
                obs = [provider.get_price(series_code)]
            else:
                obs = provider.get_series(series_code)
            written = macro_repo.upsert_observations(
                db, series_code=series_code, source=provider.name, observations=obs
            )
            db.commit()
            summary["succeeded"] += 1
            summary["rows_written"] += written
            logger.info("Ingested %d obs for %s via %s", written, series_code, provider.name)
        except Exception as exc:  # noqa: BLE001 — isolate per-series failures
            db.rollback()
            try:
                calls_repo.record(
                    db,
                    ProviderCallInfo(
                        provider=provider_name, endpoint=None, status_code=None,
                        rows_returned=None, note=f"macro ingest failed for {series_code}: {exc}",
                    ),
                )
                db.commit()
            except Exception:  # noqa: BLE001
                db.rollback()
            summary["failed"] += 1
            summary["errors"][series_code] = str(exc)
            logger.warning("Failed to ingest macro %s: %s", series_code, exc)

    if owns_session:
        db.close()
    return summary


def ingest_derivatives(tickers: list[str] | None = None, *, db: Session | None = None) -> dict:
    """Poll Binance futures positioning (funding/OI/L-S/taker) and persist it.

    Free, no key. Binance only retains ~30 days of most of these, so this runs
    on a schedule to build our own history. Isolated per-security failures are
    recorded and skipped (Guardrail 2.7); a geo-blocked futures host simply
    yields empty metrics rather than crashing.
    """
    from app.providers.derivatives_binance import BinanceDerivativesProvider

    owns_session = db is None
    db = db or SessionLocal()
    recorder = lambda info: calls_repo.record(db, info)  # noqa: E731
    provider = BinanceDerivativesProvider(call_recorder=recorder)

    if tickers:
        targets = [s for t in tickers if (s := securities_repo.get_by_ticker(db, t))]
    else:
        items, _total = securities_repo.list_securities(db, limit=1000)
        targets = list(items)

    summary = {"provider": provider.name, "requested": len(targets),
               "succeeded": 0, "failed": 0, "rows_written": 0, "errors": {}}
    for sec in targets:
        try:
            metrics = call_with_backoff(lambda: provider.get_metrics(sec.ticker), label=f"deriv:{sec.ticker}")
            written = 0
            for metric, points in metrics.items():
                written += deriv_repo.upsert_metrics(
                    db, security_id=sec.id, metric=metric, points=points
                )
            db.commit()
            if any(metrics.values()):
                summary["succeeded"] += 1
            summary["rows_written"] += written
        except Exception as exc:  # noqa: BLE001 — isolate per-security failures
            db.rollback()
            summary["failed"] += 1
            summary["errors"][sec.ticker] = str(exc)
            logger.warning("ingest_derivatives failed for %s: %s", sec.ticker, exc)

    if owns_session:
        db.close()
    return summary


def _normalise_symbol(symbol: str | None) -> str | None:
    """'NPN.JSE' -> 'NPN' for matching against our securities' tickers."""
    if not symbol:
        return None
    return symbol.split(".")[0].strip().upper()


def ingest_news(tickers: list[str] | None = None, *, db: Session | None = None) -> dict:
    """Fetch + store watchlist and general news with sentiment (§9).

    Dedupes articles by url_hash; links per-entity sentiment to matching
    securities; stores general market news with a security_id-NULL row. Never
    fabricates: unmatched entities are still recorded but not tied to a
    security. Isolated failures don't abort the job (Guardrail 2.7).
    """
    owns_session = db is None
    db = db or SessionLocal()
    recorder = lambda info: calls_repo.record(db, info)  # noqa: E731

    summary = {"provider": None, "articles": 0, "sentiments": 0, "skipped": False, "errors": {}}

    provider = get_news_provider(call_recorder=recorder)
    if provider is None:
        summary["skipped"] = True
        summary["errors"]["provider"] = "MARKETAUX_API_KEY missing"
        if owns_session:
            db.close()
        return summary
    summary["provider"] = provider.name

    # Resolve watchlist tickers -> {ticker: security_id}.
    if tickers:
        secs = [s for t in tickers if (s := securities_repo.get_by_ticker(db, t))]
    else:
        secs = [e.security for e in watchlist_repo.list_entries(db)]
    ticker_to_id = {s.ticker.upper(): s.id for s in secs}

    # --- Per-watchlist news (entity sentiment linked to securities) ---
    if ticker_to_id:
        try:
            tks = list(ticker_to_id.keys())
            articles = call_with_backoff(lambda: provider.get_news(tks), label="news:watchlist")
            for art in articles:
                row, _created = news_repo.upsert_article(db, art)
                summary["articles"] += 1
                for ent in art.entities:
                    sym = _normalise_symbol(ent.symbol)
                    sec_id = ticker_to_id.get(sym) if sym else None
                    # Only link entities we recognise; keep the raw symbol.
                    news_repo.add_sentiment(
                        db, article_id=row.id, security_id=sec_id,
                        entity_symbol=ent.symbol, sentiment=ent.sentiment,
                        relevance=ent.relevance, model=provider.name,
                    )
                    summary["sentiments"] += 1
            db.commit()
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            summary["errors"]["watchlist"] = str(exc)
            logger.warning("News ingest (watchlist) failed: %s", exc)

    # --- General market news (stored with a security_id-NULL row) ---
    try:
        general = call_with_backoff(lambda: provider.get_news([]), label="news:general")
        for art in general:
            row, _created = news_repo.upsert_article(db, art)
            summary["articles"] += 1
            news_repo.add_sentiment(
                db, article_id=row.id, security_id=None, entity_symbol=None,
                sentiment=None, relevance=None, model=provider.name,
            )
            summary["sentiments"] += 1
        db.commit()
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        summary["errors"]["general"] = str(exc)
        logger.warning("News ingest (general) failed: %s", exc)

    if owns_session:
        db.close()
    return summary


def _price_df(bars: list[PriceBar]) -> pd.DataFrame:
    """Build an ascending-by-date OHLCV DataFrame from PriceBar rows (cents)."""
    return pd.DataFrame(
        {
            "open": [float(b.open) for b in bars],
            "high": [float(b.high) for b in bars],
            "low": [float(b.low) for b in bars],
            "close": [float(b.close) for b in bars],
            "volume": [float(b.volume) if b.volume is not None else float("nan") for b in bars],
        },
        index=[b.bar_datetime for b in bars],
    )


def compute_indicators(*, db: Session | None = None) -> dict:
    """Recompute the indicator cache from stored price bars (§9)."""
    owns_session = db is None
    db = db or SessionLocal()
    summary = {"securities": 0, "rows_written": 0, "errors": {}}
    try:
        for sec_id in prices_repo.security_ids_with_bars(db):
            try:
                bars = prices_repo.get_bars(db, security_id=sec_id)
                if len(bars) < 2:
                    continue
                df = _price_df(bars)
                ci = indicators_calc.compute_indicators(df)
                rows = []
                for bar_dt, row in ci.iterrows():
                    for name in indicators_calc.INDICATOR_NAMES:
                        val = row[name]
                        rows.append(
                            {
                                "bar_datetime": bar_dt,
                                "indicator": name,
                                # store NULL for NaN (never fabricate)
                                "value": None if pd.isna(val) else float(val),
                            }
                        )
                written = indicators_repo.upsert_values(
                    db, security_id=sec_id, timeframe="1d", rows=rows
                )
                db.commit()
                summary["securities"] += 1
                summary["rows_written"] += written
            except Exception as exc:  # noqa: BLE001
                db.rollback()
                summary["errors"][str(sec_id)] = str(exc)
                logger.warning("compute_indicators failed for security %s: %s", sec_id, exc)
    finally:
        if owns_session:
            db.close()
    return summary


def generate_signals(tickers: list[str] | None = None, *, db: Session | None = None) -> dict:
    """Run the engine over target securities and write signals (§9, §10)."""
    owns_session = db is None
    db = db or SessionLocal()
    settings = settings_service.get_effective_settings(db)
    summary = {"generated": 0, "errors": {}, "targets": 0}
    try:
        # Market regime: computed once from the BTC series (crypto 'market').
        macro_series = {
            "BTC": [float(o.value) for o in macro_repo.get_series(db, series_code="BTC")]
        }
        macro_layer = macro_regime.macro_regime_score(macro_series)

        # Market-wide sentiment from the latest Fear & Greed index (0..100),
        # mapped to [-1, 1] (greed = positive). Same for every asset.
        fng = macro_repo.get_latest(db, series_code="FNG")
        fng_pairs: list[tuple[float, float]] = []
        if fng is not None:
            fng_sent = max(-1.0, min(1.0, (float(fng.value) - 50.0) / 50.0))
            fng_pairs = [(fng_sent, 1.0)] * 5  # 5 -> full conviction (no volume damping)

        # Measured hit rate -> confidence (None until Phase 6 has closed trades).
        perf = performance.measured_performance(db)
        confidence = performance.confidence_from_performance(perf)

        # Targets: requested tickers, else watchlist, else anything with bars.
        if tickers:
            targets = [s for t in tickers if (s := securities_repo.get_by_ticker(db, t))]
        else:
            targets = [e.security for e in watchlist_repo.list_entries(db)]
            if not targets:
                ids = prices_repo.security_ids_with_bars(db)
                targets = [securities_repo.get_by_id(db, i) for i in ids]
                targets = [t for t in targets if t]
        summary["targets"] = len(targets)
        summary["skipped_illiquid"] = 0
        summary["capped"] = 0
        summary["paper_trades_opened"] = 0

        # Load bars once; apply the liquidity filter (Phase B) up front.
        bars_by_id: dict[int, list] = {}
        liquid: list = []
        for sec in targets:
            bars = prices_repo.get_bars(db, security_id=sec.id)
            if len(bars) < 50:
                summary["errors"][sec.ticker] = "insufficient price history (<50 bars)"
                continue
            closes = [float(b.close) for b in bars]
            vols = [float(b.volume) if b.volume is not None else float("nan") for b in bars]
            if not momentum.is_liquid(
                closes, vols, min_zar=settings.min_liquidity_zar,
                lookback=settings.liquidity_lookback_days,
            ):
                summary["skipped_illiquid"] += 1
                continue
            bars_by_id[sec.id] = bars
            liquid.append(sec)

        # Cross-sectional momentum across the liquid set (Phase B).
        mom_values = {
            sec.id: momentum.momentum_value(
                [float(b.close) for b in bars_by_id[sec.id]],
                lookback=settings.momentum_lookback_days,
                skip=settings.momentum_skip_days,
            )
            for sec in liquid
        }
        mom_scores = momentum.cross_sectional_scores(mom_values)

        # Portfolio caps (Phase C): seed counters from currently-open trades.
        open_trades = paper_repo.list_open(db)
        open_count = len(open_trades)
        sector_counts: Counter = Counter()
        for t in open_trades:
            s = securities_repo.get_by_id(db, t.security_id)
            if s and s.sector:
                sector_counts[s.sector] += 1

        now = datetime.now()
        since = now - timedelta(days=14)
        for sec in liquid:
            try:
                df = _price_df(bars_by_id[sec.id])
                # Sentiment is market-wide (Fear & Greed) for crypto.
                sentiment_pairs = fng_pairs
                draft = signal_engine.build_signal(
                    security_id=sec.id,
                    sector=sec.sector,
                    price_df=df,
                    macro_layer=macro_layer,
                    sentiment_pairs=sentiment_pairs,
                    settings=settings,
                    generated_at=now,
                    confidence=confidence,
                    momentum_score=mom_scores.get(sec.id, 0.0),
                )
                sig = signals_repo.create(db, draft)
                summary["generated"] += 1

                # Open a paper trade for actionable BUYs, subject to portfolio
                # caps (Phase C) and one-per-security.
                if (
                    draft.direction == SignalDirection.BUY
                    and draft.suggested_entry is not None
                    and draft.suggested_size
                    and not paper_repo.has_open_for_security(db, security_id=sec.id)
                ):
                    at_global_cap = open_count >= settings.max_open_positions
                    at_sector_cap = (
                        sec.sector is not None
                        and sector_counts[sec.sector] >= settings.max_positions_per_sector
                    )
                    if at_global_cap or at_sector_cap:
                        summary["capped"] += 1
                    else:
                        paper_repo.open_trade(
                            db,
                            signal_id=sig.id,
                            security_id=sec.id,
                            entry_datetime=now,
                            entry_price=draft.suggested_entry,
                            quantity=draft.suggested_size,
                            stop_price=draft.suggested_stop,
                        )
                        open_count += 1
                        if sec.sector:
                            sector_counts[sec.sector] += 1
                        summary["paper_trades_opened"] += 1

                db.commit()
            except Exception as exc:  # noqa: BLE001
                db.rollback()
                summary["errors"][sec.ticker] = str(exc)
                logger.warning("generate_signals failed for %s: %s", sec.ticker, exc)
    finally:
        if owns_session:
            db.close()
    return summary


_SENS_NAME_SUFFIXES = (
    " limited", " ltd", " plc", " group", " holdings", " holding", " sa",
    " (rf)", " corporation", " corp", " inc", ",",
)


def _sec_index(db: Session) -> list[tuple[int, str, str]]:
    """(id, ticker, name_key) for headline matching; name_key stripped of noise."""
    idx: list[tuple[int, str, str]] = []
    items, _total = securities_repo.list_securities(db, limit=1000)
    for s in items:
        key = s.name.lower()
        for suf in _SENS_NAME_SUFFIXES:
            key = key.replace(suf, "")
        idx.append((s.id, s.ticker.upper(), key.strip()))
    return idx


def _match_security(headline: str, index: list[tuple[int, str, str]]) -> int | None:
    """Best-effort map a SENS headline to a security id (else None)."""
    hl = headline.lower()
    # Prefer an explicit ticker token, then a distinctive name match.
    for sec_id, ticker, _key in index:
        if re.search(rf"\b{re.escape(ticker)}\b", headline):
            return sec_id
    for sec_id, _ticker, key in index:
        if len(key) >= 4 and key in hl:
            return sec_id
    return None


def ingest_sens(*, db: Session | None = None) -> dict:
    """Ingest SENS announcements from the configured RSS feed (Phase D).

    Dedupes by url hash and maps each headline to a security when possible.
    A blank SENS_RSS_URL disables the job; an empty feed records zero honestly.
    """
    owns_session = db is None
    db = db or SessionLocal()
    settings = get_settings()
    summary = {"fetched": 0, "new": 0, "matched": 0, "skipped": False, "error": None}
    try:
        if not settings.sens_rss_url:
            summary["skipped"] = True
            summary["error"] = "SENS_RSS_URL not set"
            return summary
        provider = SensRssProvider(settings.sens_rss_url)
        try:
            items = call_with_backoff(provider.get_recent, label="sens")
        except Exception as exc:  # noqa: BLE001
            summary["error"] = str(exc)
            calls_repo.record(
                db,
                ProviderCallInfo(
                    provider="sens_rss", endpoint=settings.sens_rss_url, status_code=None,
                    rows_returned=None, note=f"fetch failed: {exc}",
                ),
            )
            db.commit()
            return summary

        summary["fetched"] = len(items)
        index = _sec_index(db)
        for item in items:
            sec_id = _match_security(item.headline, index)
            _row, created = sens_repo.upsert(
                db,
                source=provider.name,
                url=item.url,
                headline=item.headline,
                summary=item.summary,
                category=item.category,
                published_at=item.published_at,
                security_id=sec_id,
                raw=item.raw,
            )
            if created:
                summary["new"] += 1
            if sec_id is not None:
                summary["matched"] += 1
        calls_repo.record(
            db,
            ProviderCallInfo(
                provider="sens_rss", endpoint=settings.sens_rss_url, status_code=200,
                rows_returned=len(items), note=f"{summary['new']} new",
            ),
        )
        db.commit()
    finally:
        if owns_session:
            db.close()
    return summary


def enrich_sectors(*, db: Session | None = None) -> dict:
    """No-op for crypto: asset categories are set at seed time. Kept so the
    JOBS registry / any schedule reference stays valid."""
    return {"updated": 0, "note": "crypto categories are set at seed time"}


def update_paper_trades(*, db: Session | None = None) -> dict:
    """Mark open paper trades to market; close on stop/horizon; compute net P&L (§9).

    Exit and costs are handled by the pure ``app.signals.paper`` logic so the
    accounting is deterministic and testable.
    """
    owns_session = db is None
    db = db or SessionLocal()
    settings = settings_service.get_effective_settings(db)
    costs = paper.Costs(
        brokerage_pct=settings.brokerage_pct,
        slippage_pct=settings.slippage_pct,
        stt_pct=settings.stt_pct,
    )
    summary = {"open_before": 0, "closed": 0, "still_open": 0, "errors": {}}
    try:
        open_trades = paper_repo.list_open(db)
        summary["open_before"] = len(open_trades)
        for trade in open_trades:
            try:
                sig = signals_repo.get(db, trade.signal_id) if trade.signal_id else None
                horizon = sig.horizon_days if sig else settings.default_horizon_days

                bars = prices_repo.get_bars(
                    db, security_id=trade.security_id, start=trade.entry_datetime.date()
                )
                bar_lites = [
                    paper.BarLite(bar_datetime=b.bar_datetime, high=b.high, low=b.low, close=b.close)
                    for b in bars
                ]
                decision = paper.evaluate_exit(
                    entry_datetime=trade.entry_datetime,
                    stop_price=trade.stop_price,
                    horizon_days=horizon,
                    bars=bar_lites,
                    entry_price=trade.entry_price,
                    trailing_pct=settings.trailing_stop_pct,
                )
                if decision is None:
                    summary["still_open"] += 1
                    continue

                pnl = paper.net_pnl(
                    entry_price=trade.entry_price,
                    exit_price=decision.exit_price,
                    quantity=trade.quantity,
                    costs=costs,
                )
                paper_repo.close_trade(
                    db,
                    trade=trade,
                    exit_datetime=decision.exit_datetime,
                    exit_price=decision.exit_price,
                    pnl=pnl,
                )
                db.commit()
                summary["closed"] += 1
                logger.info(
                    "Closed paper trade %s (%s) pnl=%s cents", trade.id, decision.reason, pnl
                )
            except Exception as exc:  # noqa: BLE001
                db.rollback()
                summary["errors"][str(trade.id)] = str(exc)
                logger.warning("update_paper_trades failed for trade %s: %s", trade.id, exc)
    finally:
        if owns_session:
            db.close()
    return summary


# Registry of jobs callable by name from the admin run-job endpoint.
JOBS: dict[str, callable] = {
    "ingest_daily_prices": ingest_daily_prices,
    "ingest_macro": ingest_macro,
    "ingest_derivatives": ingest_derivatives,
    "ingest_news": ingest_news,
    "compute_indicators": compute_indicators,
    "generate_signals": generate_signals,
    "update_paper_trades": update_paper_trades,
    "enrich_sectors": enrich_sectors,
    "ingest_sens": ingest_sens,
}
