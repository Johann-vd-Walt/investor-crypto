# PROJECT_SPEC.md — JSE Swing-Trading Decision-Support App

> **How to use this file with Claude in VS Code.**
> Place this file at the root of the repository. When working with Claude Code, point it at this file and build **one task at a time**, working top-to-bottom through the phased checklist in Section 13. After each task, run the tests and review the diff before moving on. Ask Claude to update the "Progress log" at the bottom as tasks complete. Do not let it implement several phases at once.

---

## 1. What this app is (and is not)

**Is:** A personal, desktop web application that continuously ingests delayed JSE price data, macro-economic indicators (oil, gold, USD/ZAR, index levels), and local plus international news, then produces explainable buy/sell/hold **signals** for short-hold trades (roughly 1 to 14 days) on JSE-listed shares.

**Is not:** It does **not** place trades. It does not connect to a broker. It does not advise anyone other than the single owner. It is decision-support only.

### Locked decisions (do not revisit without owner approval)
- Personal use only. No multi-user, no accounts system, no advice-to-others features. (This keeps it outside FSCA/FAIS licensing.)
- Decision-support only. No order execution, no broker integration.
- Delayed or end-of-day data is acceptable. Do not build for real-time tick data.
- Desktop web only. No mobile app. Responsive-desktop is enough.
- Local JSE market only. No offshore markets.
- Stack: **Python + FastAPI + React + MySQL 8**.

---

## 2. Guardrails for the coding assistant

These are hard rules. Follow them in every task.

1. **Never commit secrets.** All API keys and the database URL live in `.env`, loaded via config. Provide `.env.example` with blank values only.
2. **Money is `DECIMAL`, never float.** All prices, fees, and P&L use `DECIMAL`. Floating point corrupts financial arithmetic.
3. **JSE prices are quoted in South African cents (ZAc).** A share shown as "R100.00" is stored/returned by many feeds as `10000`. Normalise consistently at the ingestion boundary, store one canonical unit (cents), and convert to Rand only in the presentation layer. Document the chosen convention in `README.md` and never mix units.
4. **Database access goes through a data-access layer** (SQLAlchemy models plus repository/service functions). No raw SQL scattered through the app. This keeps a future move to PostgreSQL/TimescaleDB contained.
5. **Every external provider sits behind the `providers/base.py` interface.** No provider-specific code leaks into the signal engine or API layer.
6. **Respect provider rate limits.** Free tiers are small. Cache responses, batch requests, and log every call in `provider_calls`. Never hammer an API in a loop without backoff.
7. **Do not fabricate data.** If a feed fails or returns nothing, record the failure and surface it. Never fill gaps with invented values. Never silently serve stale data as if it were fresh: carry an `is_delayed` / `as_of` timestamp through to the UI.
8. **Signals are estimates, not predictions.** The UI must always show the signal's reasoning and the engine's measured historical hit rate. No hidden "black box confidence".
9. **Use migrations (Alembic).** Never hand-edit the live schema; every schema change is a migration.
10. **Write type hints and Pydantic schemas** for all API inputs and outputs. Write tests for the signal engine and ingestion parsers.
11. **Small, reviewable changes.** One task per commit. Ask before any large refactor.

---

## 3. Architecture overview

```
                    +---------------------------+
   External APIs -->|  Ingestion workers        |
   (prices, macro,  |  (APScheduler jobs)       |
    commodities,    +------------+--------------+
    news)                        |
                                 v
                        +--------+--------+
                        |     MySQL 8     |  <-- durable storage
                        +--------+--------+
                                 ^
                                 |
             +-------------------+-------------------+
             |                                       |
      +------+-------+                        +------+-------+
      | Signal engine |  (pandas compute)     |  FastAPI     |
      | indicators,   |---------------------->|  REST API    |
      | regime,       |    writes signals     +------+-------+
      | sentiment,    |                               |
      | fusion        |                               v
      +---------------+                        +-------+------+
                                               | React (web)  |
                                               |  dashboard   |
                                               +--------------+
```

Key point: the heavy time-series maths happens **in pandas, in memory**, not in SQL. MySQL is durable storage. This is why MySQL is sufficient for this scope.

---

## 4. Technology and versions

| Layer | Choice | Notes |
|---|---|---|
| Language | Python 3.12+ | |
| Web framework | FastAPI | Async, Pydantic validation, auto OpenAPI docs |
| ASGI server | Uvicorn | |
| ORM | SQLAlchemy 2.0 | |
| Migrations | Alembic | |
| DB driver | PyMySQL (or mysqlclient) | |
| Data/compute | pandas, numpy | |
| Indicators | pandas-ta (pure Python, easy install) | TA-Lib optional if you want C-speed and can install it |
| Scheduling | APScheduler | In-process scheduler is enough at this scale |
| HTTP client | httpx | Async-friendly |
| Database | MySQL 8.x | Needs window functions, CTEs, JSON |
| Frontend | React 18 + Vite + TypeScript | |
| Charts | lightweight-charts (candlesticks) + Recharts (everything else) | |
| Data fetching (FE) | TanStack Query | Caching, refetch, loading states |
| Testing | pytest (BE), Vitest + React Testing Library (FE) | |

---

## 5. Repository structure

```
jse-swingtrader/
  backend/
    app/
      main.py                  # FastAPI app factory, router registration
      config.py                # Pydantic Settings, loads .env
      db/
        session.py             # engine + session
        models.py              # SQLAlchemy models (Section 7)
      migrations/              # Alembic
      providers/
        base.py                # abstract provider interfaces
        prices_eodhd.py
        prices_yahoo.py        # fallback / prototype only
        macro_alphavantage.py
        commodities_oilprice.py
        news_marketaux.py
        registry.py            # picks active provider per data family
      ingestion/
        scheduler.py           # APScheduler setup
        jobs.py                # job functions + cadences
      signals/
        indicators.py          # SMA/EMA/RSI/MACD/ATR via pandas-ta
        technical.py           # per-stock technical score
        macro_regime.py        # market-wide regime score
        sentiment.py           # per-stock news sentiment score
        engine.py              # fusion + rationale + signal writing
        performance.py         # measured hit rate / paper P&L
      schemas/                 # Pydantic request/response models
      api/
        routes_health.py
        routes_securities.py
        routes_watchlist.py
        routes_prices.py
        routes_macro.py
        routes_news.py
        routes_signals.py
        routes_trades.py
        routes_paper.py
    tests/
    requirements.txt
    .env.example
    alembic.ini
  frontend/
    src/
      api/client.ts            # typed API client
      pages/
        Dashboard.tsx
        Watchlist.tsx
        SecurityDetail.tsx
        Signals.tsx
        Journal.tsx
        PaperPerformance.tsx
        Settings.tsx
      components/
      App.tsx
      main.tsx
    package.json
    vite.config.ts
  README.md
  docker-compose.yml           # optional: MySQL + backend for local dev
```

---

## 6. Configuration and secrets

`backend/.env.example`:

```
# Database
DATABASE_URL=mysql+pymysql://jse_user:changeme@localhost:3306/jse_swingtrader

# Data providers (fill in your own keys; leave blank to disable a provider)
EODHD_API_KEY=
ALPHAVANTAGE_API_KEY=
MARKETAUX_API_KEY=
OILPRICE_API_KEY=

# App
APP_ENV=development
LOG_LEVEL=INFO
# Signal engine weights (must sum to 1.0)
WEIGHT_TECHNICAL=0.5
WEIGHT_MACRO=0.2
WEIGHT_SENTIMENT=0.3
DEFAULT_HORIZON_DAYS=10
```

`config.py` loads these with Pydantic `BaseSettings`. The app must start cleanly with any provider key missing, disabling that provider and logging a warning rather than crashing.

---

## 7. Database schema (MySQL 8)

Implement as SQLAlchemy models and generate the initial Alembic migration from them. DDL shown here is the target shape.

```sql
-- Reference data for each tradable instrument
CREATE TABLE securities (
  id          INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  ticker      VARCHAR(12)  NOT NULL UNIQUE,   -- JSE code, e.g. 'NPN'
  isin        VARCHAR(12)  NULL,
  name        VARCHAR(255) NOT NULL,
  sector      VARCHAR(100) NULL,
  currency    CHAR(3)      NOT NULL DEFAULT 'ZAR',
  is_active   BOOLEAN      NOT NULL DEFAULT TRUE,
  created_at  TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at  TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- OHLCV bars. Prices stored in cents (ZAc). Composite PK is the key to speed.
CREATE TABLE price_bars (
  security_id  INT UNSIGNED  NOT NULL,
  timeframe    VARCHAR(5)    NOT NULL,          -- '1d' now; '1m' later
  bar_datetime DATETIME      NOT NULL,
  open         DECIMAL(15,4) NOT NULL,
  high         DECIMAL(15,4) NOT NULL,
  low          DECIMAL(15,4) NOT NULL,
  close        DECIMAL(15,4) NOT NULL,
  adj_close    DECIMAL(15,4) NULL,
  volume       BIGINT UNSIGNED NULL,
  source       VARCHAR(40)   NOT NULL,
  is_delayed   BOOLEAN       NOT NULL DEFAULT TRUE,
  ingested_at  TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (security_id, timeframe, bar_datetime),
  CONSTRAINT fk_pricebars_sec FOREIGN KEY (security_id) REFERENCES securities(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Cached computed indicators (tall/flexible). Recompute is cheap; this is a cache.
CREATE TABLE indicator_values (
  security_id  INT UNSIGNED  NOT NULL,
  timeframe    VARCHAR(5)    NOT NULL,
  bar_datetime DATETIME      NOT NULL,
  indicator    VARCHAR(40)   NOT NULL,          -- 'sma_20','rsi_14','macd_line', etc.
  value        DECIMAL(18,6) NULL,
  computed_at  TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (security_id, timeframe, bar_datetime, indicator),
  CONSTRAINT fk_ind_sec FOREIGN KEY (security_id) REFERENCES securities(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Macro, commodity, FX and index series
CREATE TABLE macro_series (
  series_code      VARCHAR(30)   NOT NULL,      -- 'BRENT','WTI','GOLD','USDZAR','JSE_ALSI','JSE_TOP40','US_CPI','SA_REPO'
  observation_date DATE          NOT NULL,
  value            DECIMAL(18,6) NOT NULL,
  unit             VARCHAR(30)   NULL,
  source           VARCHAR(40)   NOT NULL,
  ingested_at      TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (series_code, observation_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Raw news articles, deduplicated by url hash
CREATE TABLE news_articles (
  id           BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  source       VARCHAR(80)  NOT NULL,
  url          VARCHAR(768) NOT NULL,
  url_hash     CHAR(64)     NOT NULL UNIQUE,    -- sha256(url)
  title        VARCHAR(512) NOT NULL,
  snippet      TEXT         NULL,
  published_at DATETIME     NULL,
  language     VARCHAR(8)   NULL,
  raw          JSON         NULL,
  fetched_at   TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_news_published (published_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Article-to-security sentiment links
CREATE TABLE news_sentiment (
  id            BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  article_id    BIGINT UNSIGNED NOT NULL,
  security_id   INT UNSIGNED   NULL,            -- NULL = general macro/market news
  entity_symbol VARCHAR(40)    NULL,
  sentiment     DECIMAL(6,4)   NULL,            -- -1.0000 .. 1.0000
  relevance     DECIMAL(6,4)   NULL,
  model         VARCHAR(40)    NULL,            -- which scorer produced it
  created_at    TIMESTAMP      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_sent_article FOREIGN KEY (article_id) REFERENCES news_articles(id) ON DELETE CASCADE,
  CONSTRAINT fk_sent_sec     FOREIGN KEY (security_id) REFERENCES securities(id),
  INDEX idx_sent_sec (security_id, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Generated signals with full explainability
CREATE TABLE signals (
  id              BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  security_id     INT UNSIGNED  NOT NULL,
  generated_at    DATETIME      NOT NULL,
  horizon_days    SMALLINT      NOT NULL DEFAULT 10,
  direction       ENUM('BUY','SELL','HOLD') NOT NULL,
  score           DECIMAL(6,4)  NOT NULL,       -- fused score, -1..1
  confidence      DECIMAL(6,4)  NULL,           -- from measured historical hit rate
  technical_score DECIMAL(6,4)  NULL,
  macro_score     DECIMAL(6,4)  NULL,
  sentiment_score DECIMAL(6,4)  NULL,
  suggested_entry DECIMAL(15,4) NULL,
  suggested_stop  DECIMAL(15,4) NULL,
  suggested_size  INT           NULL,
  rationale       JSON          NULL,           -- structured reasons per layer
  status          ENUM('OPEN','ACTED','EXPIRED','DISMISSED') NOT NULL DEFAULT 'OPEN',
  CONSTRAINT fk_sig_sec FOREIGN KEY (security_id) REFERENCES securities(id),
  INDEX idx_sig_gen (generated_at),
  INDEX idx_sig_sec (security_id, generated_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE watchlist (
  id          INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  security_id INT UNSIGNED NOT NULL UNIQUE,
  added_at    TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
  notes       VARCHAR(500) NULL,
  CONSTRAINT fk_wl_sec FOREIGN KEY (security_id) REFERENCES securities(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Real trades you actually placed (manual entry). Doubles as the tax record.
CREATE TABLE trades (
  id               BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  security_id      INT UNSIGNED  NOT NULL,
  side             ENUM('BUY','SELL') NOT NULL,
  quantity         INT           NOT NULL,
  price            DECIMAL(15,4) NOT NULL,
  fees             DECIMAL(15,4) NOT NULL DEFAULT 0,
  trade_datetime   DATETIME      NOT NULL,
  linked_signal_id BIGINT UNSIGNED NULL,
  rationale        VARCHAR(1000) NULL,
  created_at       TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_trade_sec FOREIGN KEY (security_id) REFERENCES securities(id),
  CONSTRAINT fk_trade_sig FOREIGN KEY (linked_signal_id) REFERENCES signals(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Simulated trades so the engine can measure itself before real money is used
CREATE TABLE paper_trades (
  id             BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  signal_id      BIGINT UNSIGNED NULL,
  security_id    INT UNSIGNED   NOT NULL,
  entry_datetime DATETIME       NOT NULL,
  entry_price    DECIMAL(15,4)  NOT NULL,
  quantity       INT            NOT NULL,
  stop_price     DECIMAL(15,4)  NULL,
  exit_datetime  DATETIME       NULL,
  exit_price     DECIMAL(15,4)  NULL,
  pnl            DECIMAL(15,4)  NULL,
  status         ENUM('OPEN','CLOSED') NOT NULL DEFAULT 'OPEN',
  CONSTRAINT fk_paper_sec FOREIGN KEY (security_id) REFERENCES securities(id),
  CONSTRAINT fk_paper_sig FOREIGN KEY (signal_id) REFERENCES signals(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Rate-limit and health tracking for every external call
CREATE TABLE provider_calls (
  id            BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  provider      VARCHAR(40) NOT NULL,
  endpoint      VARCHAR(255) NULL,
  called_at     TIMESTAMP   NOT NULL DEFAULT CURRENT_TIMESTAMP,
  status_code   INT         NULL,
  rows_returned INT         NULL,
  note          VARCHAR(255) NULL,
  INDEX idx_prov (provider, called_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

### Scale sanity check
Full JSE universe (about 430 names) of daily bars over 10 years is roughly 1 million rows: trivial for MySQL. Even one-minute bars for the whole universe is roughly 50 million rows per year, still fine with the composite primary key above. You will realistically only store intraday data for a watchlist, so real volumes are far smaller. If you ever move to real-time full-universe tick storage, migrate to PostgreSQL + TimescaleDB; the data-access layer (guardrail 4) makes that contained rather than a rewrite.

---

## 8. Data providers

Each provider is a class implementing a family interface in `providers/base.py`. Confirm exact endpoints, response shapes, and current free-tier limits against each provider's live docs during implementation. Do not assume the example shapes below are exact.

| Family | Primary provider | Fallback / prototype | Notes |
|---|---|---|---|
| JSE prices (EOD) | EODHD (`{TICKER}.JSE`) | Yahoo Finance (`{TICKER}.JO`, unofficial) | Delayed / end-of-day. Handle ZAc cents. |
| Fundamentals | EODHD | none for now | Sector, name, ISIN for `securities` |
| Commodities (oil, gold) | OilPriceAPI (energy), a metals API for gold | Alpha Vantage (WTI, Brent) | Small free tiers; cache hard |
| FX (USD/ZAR) | Alpha Vantage forex | EODHD forex | Daily is fine |
| US/SA macro | Alpha Vantage economic endpoints; FRED (free) | SARB / Stats SA (may need scheduled scraping) | Repo rate, CPI, yields |
| News + sentiment | Marketaux (ticker-tagged, -1..1 sentiment) | Alpha Vantage News & Sentiment | Plus a broad aggregator for general headlines |
| JSE company announcements | JSE SENS | none | Authoritative for corporate actions; integrate when feasible |

`providers/base.py` interfaces to define:
- `PriceProvider.get_daily_bars(ticker, start, end) -> list[Bar]`
- `MacroProvider.get_series(series_code, start, end) -> list[Observation]`
- `CommodityProvider.get_price(code) -> Observation`
- `NewsProvider.get_news(tickers, since) -> list[Article]` (with entities + sentiment where available)

`registry.py` reads config and returns the active provider per family, skipping any whose key is missing.

---

## 9. Ingestion design

APScheduler jobs in `ingestion/jobs.py`. All jobs: log to `provider_calls`, dedupe on write, mark `is_delayed`, back off on HTTP 429, and never crash the scheduler on a single failure.

| Job | Cadence (suggested) | Action |
|---|---|---|
| `ingest_daily_prices` | Once after JSE close (about 18:00 SAST) on trading days | Pull EOD bars for all watchlist + screening securities |
| `ingest_macro` | 2 to 3 times a day | Oil, gold, USD/ZAR, index levels, key rates |
| `ingest_news` | Hourly | Watchlist + sector + general market news, store + score |
| `compute_indicators` | Nightly, after prices | Recompute indicator cache from pandas |
| `generate_signals` | Nightly, after indicators | Run the engine, write to `signals`, open matching `paper_trades` |
| `update_paper_trades` | Nightly | Mark-to-market open paper trades, close on stop/horizon, compute P&L |

Provide a manual trigger endpoint (`POST /api/admin/run-job`) for development so jobs can be fired on demand.

---

## 10. Signal engine

Located in `signals/`. Compute in pandas. Keep every layer transparent.

**Technical layer (`technical.py`)** produces a score in -1..1 per security from a days-to-weeks horizon toolkit: SMA/EMA crossovers, RSI (overbought/oversold), MACD, breakout with volume confirmation, and ATR for volatility-based stop distance.

**Macro regime layer (`macro_regime.py`)** produces a market-wide score and a named regime (for example "weak rand, rising gold") from oil, gold, USD/ZAR, index trend, and rates. It tilts scores by sector: a gold-friendly regime lifts gold miners, and so on.

**Sentiment layer (`sentiment.py`)** produces a per-security score from recent news sentiment and headline volume, plus an event flag (upcoming results, dividends, SENS items).

**Fusion (`engine.py`)** combines the three using the configurable weights from `.env` (`WEIGHT_TECHNICAL`, `WEIGHT_MACRO`, `WEIGHT_SENTIMENT`, must sum to 1.0). It writes each signal with:
- `direction` from thresholds on the fused score,
- `suggested_entry`, `suggested_stop` (from ATR), `suggested_size` (from a fixed risk-per-trade rule, for example risk no more than 1 to 2 percent of a configurable account size),
- a structured `rationale` JSON listing exactly which sub-signals fired in each layer,
- `confidence` from the engine's own measured historical hit rate for similar past signals (see below).

**Performance (`performance.py`)** continuously computes the win rate and average return of past signals using `paper_trades`. The UI must display this. If measured edge is weak, that must be visible, not hidden.

### Honesty requirements
- Backtests must include realistic costs (brokerage, spread, slippage) and must be out-of-sample. A cost-free backtest is misleading and must not be shipped as the headline number.
- Paper trading runs before any real-money use. The `trades` table (real) stays separate from `paper_trades` (simulated).

---

## 11. Backend API (FastAPI)

All responses are Pydantic models. All list endpoints paginate. Prices returned in Rand with an explicit `as_of` and `is_delayed` field.

```
GET    /api/health

GET    /api/securities?query=&sector=&active=
GET    /api/securities/{ticker}

GET    /api/watchlist
POST   /api/watchlist            { ticker, notes? }
DELETE /api/watchlist/{id}

GET    /api/prices/{ticker}?timeframe=1d&from=&to=
GET    /api/indicators/{ticker}?timeframe=1d&names=sma_20,rsi_14

GET    /api/macro                # dashboard snapshot: oil, gold, USDZAR, indices, rates
GET    /api/macro/{series_code}?from=&to=

GET    /api/news?ticker=&since=&limit=
GET    /api/news/general?since=&limit=

GET    /api/signals?date=&direction=&min_score=
GET    /api/signals/{id}         # includes full rationale
POST   /api/signals/{id}/status  { status }   # ACTED / DISMISSED

GET    /api/trades               # journal
POST   /api/trades               { ticker, side, quantity, price, fees, trade_datetime, linked_signal_id?, rationale? }
GET    /api/trades/tax-summary?tax_year=       # realised trades summary for SARS record-keeping

GET    /api/paper/performance    # win rate, avg return, equity curve
GET    /api/paper/trades

POST   /api/admin/run-job        { job_name }  # dev only
```

Enable CORS for the Vite dev server origin. Serve OpenAPI docs at `/docs`.

---

## 12. Frontend (React)

Desktop web, TypeScript, Vite, TanStack Query for data fetching, lightweight-charts for candlesticks, Recharts for the rest. Every screen that shows prices must display the `as_of` timestamp and a clear "delayed" badge.

| Page | Contents |
|---|---|
| **Dashboard** | Macro snapshot (oil, gold, USD/ZAR, Top 40 / All-Share, key rates), today's top-ranked signals, market breadth, data-freshness banner |
| **Watchlist** | Add/remove JSE tickers, latest delayed price, today's signal per name |
| **Security detail** | Candlestick chart with indicator overlays, signal history, per-name news feed with sentiment, upcoming events |
| **Signals** | Ranked, filterable list; click through to full rationale; mark Acted/Dismissed |
| **Journal** | Log real trades, view P&L, export tax summary |
| **Paper performance** | Equity curve, win rate, average return, honest measured hit rate |
| **Settings** | Signal weights and thresholds, risk-per-trade and account size, which providers are active, data-freshness status |

---

## 13. Phased build plan (work through in order)

### Phase 0 — Scaffolding
- [ ] Create repo structure (Section 5), Python venv, `requirements.txt`, Vite React TS app.
- [ ] `config.py` with Pydantic Settings and `.env.example`. App starts with missing keys, logging warnings.
- [ ] MySQL 8 connection via SQLAlchemy; `/api/health` returns DB status.
- [ ] Alembic initialised.

### Phase 1 — Data model and reference data
- [ ] Implement all SQLAlchemy models (Section 7); generate and apply the initial migration.
- [ ] Seed `securities` from EODHD JSE listing (name, sector, ISIN). Handle the ZAc cents convention and document it.
- [ ] Watchlist CRUD endpoints and page.

### Phase 2 — Price ingestion and charts
- [ ] `PriceProvider` interface + EODHD implementation (+ Yahoo fallback for prototyping).
- [ ] `ingest_daily_prices` job + manual trigger. Log to `provider_calls`.
- [ ] Prices and indicators endpoints.
- [ ] Security detail page with candlestick chart. Delayed badge visible.

### Phase 3 — Macro, commodities, FX
- [ ] Macro/commodity/FX providers and `ingest_macro` job.
- [ ] `/api/macro` snapshot endpoint.
- [ ] Dashboard macro panel.

### Phase 4 — News and sentiment
- [ ] `NewsProvider` (Marketaux primary), dedupe by url hash, store sentiment.
- [ ] `ingest_news` job.
- [ ] News endpoints and per-security news feed.

### Phase 5 — Signal engine
- [ ] `indicators.py`, `technical.py`, `macro_regime.py`, `sentiment.py`, `engine.py`.
- [ ] `compute_indicators` and `generate_signals` jobs.
- [ ] Signals endpoints and pages, with full rationale display.
- [ ] Unit tests for each layer and for fusion.

### Phase 6 — Paper trading and performance
- [ ] Open paper trades from signals; `update_paper_trades` job; P&L and stop/horizon logic.
- [ ] `performance.py` (win rate, average return, equity curve).
- [ ] Paper performance page.

### Phase 7 — Trade journal and tax
- [ ] Journal CRUD, link trades to signals.
- [ ] Tax-summary export for a chosen tax year.

### Phase 8 — Backtesting and tuning
- [ ] Backtester with realistic costs, out-of-sample.
- [ ] Settings page for weights, thresholds, risk-per-trade, account size.

### Phase 9 — Hardening
- [ ] Rate-limit backoff and caching review across all providers.
- [ ] Data-freshness surfacing everywhere prices appear.
- [ ] Error states in the UI; graceful degradation when a feed is down.
- [ ] README with setup, run, and the units/cents convention.

---

## 14. Testing strategy
- **Providers:** test parsers against saved sample responses (fixtures), not live calls.
- **Signal engine:** deterministic unit tests on known price series with expected indicator and score outputs.
- **API:** endpoint tests with a test database.
- **Frontend:** component tests for the dashboard, signal list, and journal.

---

## 15. Disclaimers (keep visible in the app footer)
This is a personal decision-support tool, not financial, tax, or legal advice, and not a broker. It does not place trades. Signals are probabilistic estimates and can be wrong. Trading carries a real risk of loss. Short-term frequent trading may be taxed as income rather than capital gains in South Africa; confirm your situation with a registered tax practitioner. Verify all provider licence terms before use.

---

## CRYPTO REWORK (2026-08-13) — current state

The app was reworked from JSE equities to **crypto** (Bitcoin + major altcoins),
reusing the architecture. Everything below this section describing JSE phases is
historical context; the crypto specifics supersede it.

- **Data:** Binance public klines (`data-api.binance.vision`, no key), daily bars.
  Seeded 22 major USDT pairs; ingested ~9y history (55,546 bars, 499,914 indicators).
- **Units:** native quote price (USDT), `DECIMAL(24,10)`; the cents/Rand
  convention is gone (converters are identity passthroughs).
- **Market regime:** BTC trend (crypto ≈ BTC-correlated). **Sentiment:** crypto
  Fear & Greed index (alternative.me). Both market-wide.
- **Costs:** exchange fee (~0.1%/side) + slippage; STT removed (=0). Backtest
  benchmark = **BTC buy-and-hold**.
- **Scheduling:** 24/7 (no weekday restriction).
- **Recommended platforms:** data = Binance (no key); wallet/API = VALR (SA) or Luno.
- **Safety decision:** kept **decision-support only** — NO unattended live order
  execution. Signals + paper trades + backtests only; you execute manually.
- **Legacy JSE providers/tests removed** (Yahoo/EODHD/AlphaVantage/OilPrice, SENS
  map). News RSS repointed to a crypto feed (optional).
- **Verified:** pytest 72 passing; frontend build passes; live API smoke OK
  (prices/macro/securities/momentum-backtest/pinescript).
- **Honest finding:** cross-sectional momentum (top-5, monthly) returned ~+47%
  over the window with an **−80% drawdown**, while simply **holding BTC returned
  ~+1381%**. As with the JSE version, buy-and-hold crushed the active strategy —
  the app is measuring honestly. NOT proven; not for real money.

## AUTH (2026-08-14)
Added a global **TOTP login gate** (Google Authenticator; single owner, no
users/RBAC). Server-enforced middleware gates all `/api/*` except `/api/auth/*`
and `/api/health`; login verifies a 6-digit code (pyotp) and issues a short-lived
signed JWT (PyJWT) the frontend sends as a Bearer token. **Off by default** (blank
`TOTP_SECRET`) so no lock-out; `python -m app.auth_setup` generates a secret + QR
and writes it to `.env`. Frontend `AuthGate` shows a lock screen + "Lock" button.
Verified: enabled path (401 → login → 200) and disabled path (open); 77 tests pass.

## Progress log
_(Claude: append one line per completed task, newest at the bottom.)_
- 2026-07-20 — Phase 0: created repo structure (backend/ + frontend/), Python 3.14 venv, requirements.txt.
- 2026-07-20 — Phase 0: config.py (Pydantic Settings) + .env.example; app boots with missing keys, logging per-provider warnings.
- 2026-07-20 — Phase 0: SQLAlchemy engine/session + /api/health reporting DB + provider status (returns 200 "degraded" when DB down, never crashes).
- 2026-07-20 — Phase 0: Alembic initialised, env.py wired to app settings (DATABASE_URL) and Base.metadata for autogenerate.
- 2026-07-20 — Phase 0: Vite + React 18 + TypeScript frontend scaffolded; production build verified.
- 2026-07-20 — Phase 0: README with setup + ZAc cents units convention; pytest health tests (2 passing). Phase 0 complete.
- 2026-07-20 — Phase 1: all 11 SQLAlchemy models implemented (§7); initial Alembic migration e4ce7aee8ad4 generated and applied to MySQL.
- 2026-07-20 — Phase 1: repository data-access layer (securities, watchlist) — no raw SQL in the API layer (Guardrail 2.4).
- 2026-07-20 — Phase 1: securities read endpoints (GET /api/securities, /{ticker}) + watchlist CRUD (GET/POST/DELETE), all Pydantic-typed.
- 2026-07-20 — Phase 1: securities seed (EODHD path when key set; 15-name real-JSE manual fallback with ISINs left NULL, not fabricated). Seeded 15 rows.
- 2026-07-20 — Phase 1: frontend typed API client + Watchlist page (TanStack Query), data-freshness banner, disclaimer footer (§15). Build passes.
- 2026-07-20 — Phase 1: verified live — uvicorn boot, health ok/DB connected, securities + watchlist HTTP roundtrip; pytest 5 passing. Phase 1 complete.
- 2026-07-20 — Phase 2 (owner decision): Yahoo (.JO) set as PRIMARY price provider, EODHD optional, via PRICE_PROVIDER config — chosen because EODHD free tier (20 calls/day) is insufficient for per-symbol daily ingestion.
- 2026-07-20 — Phase 2 (env): pandas-ta/numba have no Python 3.14 wheel; dropped in favour of computing the 5 indicators in pandas (Phase 5). pandas 3.0.3 / numpy 2.5.1 install fine.
- 2026-07-20 — Phase 2: providers/base.py interfaces (PriceProvider + Bar in cents + call-recorder); Yahoo provider normalises ZAc→cents off meta.currency; EODHD provider (unverified, flagged); registry.
- 2026-07-20 — Phase 2: price_bars repository (idempotent upsert), ingest_daily_prices job (per-security isolation, 429 backoff, logs provider_calls), APScheduler (18:00 Mon-Fri), POST /api/admin/run-job manual trigger.
- 2026-07-20 — Phase 2: GET /api/prices/{ticker} (cents→Rand, as_of + is_delayed) and GET /api/indicators/{ticker} (reads cache, empty until Phase 5).
- 2026-07-20 — Phase 2: frontend SecurityDetail page — lightweight-charts candlesticks, DELAYED badge + as_of, refresh-prices action, react-router wiring; watchlist tickers link through.
- 2026-07-20 — Phase 2: verified live — ingested NPN/SOL/MTN via Yahoo, /api/prices returns Rand (NPN R855.70, MTN R223.83), run-job works; pytest 14 passing (incl. Yahoo parser fixture tests). Phase 2 complete.
- 2026-07-20 — Phase 3: probed live provider shapes (confirmed, not assumed, §8); found AV free tier ~25/day & throttles FX, so sourced USD/ZAR + GOLD + JSE ALSI(^J203.JO)/Top40(^J200.JO) from Yahoo (keyless, daily).
- 2026-07-20 — Phase 3: macro providers — AlphaVantage (WTI/BRENT/CPI monthly), OilPrice (Brent spot), Yahoo macro (raw native units, no cents conversion); registry MACRO_SERIES_PLAN + honest SA_REPO gap.
- 2026-07-20 — Phase 3: macro_series repository, ingest_macro job (per-series isolation, provider_calls logging), scheduler @08/13/18 Mon-Fri, JOBS entry.
- 2026-07-20 — Phase 3: GET /api/macro snapshot (surfaces SA_REPO as unavailable) + GET /api/macro/{series_code}; dashboard macro-panel page with refresh, nav (Dashboard/Watchlist).
- 2026-07-20 — Phase 3: verified live — ingest_macro wrote 7/8 series (WTI $84.81, Brent $88.13, Gold $4016, USDZAR 16.51, ALSI 108936, Top40 100614, CPI 333.95); pytest 21 passing. Phase 3 complete (SA_REPO deferred — no free source).
- 2026-07-20 — Bugfix: Pydantic serialised Decimal as JSON string, breaking frontend .toFixed(); added DecimalAsFloat presentation type (Decimal internally, JSON number on the wire) for prices/macro/indicators/news; regression tests added.
- 2026-07-20 — Phase 4: probe found supplied MARKETAUX_API_KEY returns HTTP 401; built Marketaux provider/parser against documented shape (flagged UNVERIFIED), Article revised to carry multiple entities.
- 2026-07-20 — Phase 4: news repository (dedupe by url_hash=sha256, per-security + general sentiment rows), ingest_news job (watchlist + general, isolates failures), scheduled hourly, JOBS entry.
- 2026-07-20 — Phase 4: GET /api/news?ticker= and GET /api/news/general endpoints; frontend NewsFeed with sentiment badges — per-ticker feed on SecurityDetail, general news on Dashboard.
- 2026-07-20 — Phase 4: fixed MySQL-incompatible NULLS LAST in news ordering; verified — endpoints return 200 (empty, honest) / 404, ingest_news handles 401 gracefully; pytest 26 passing. Phase 4 complete (live news blocked on a valid Marketaux key).
- 2026-07-20 — Phase 4 (valid key added): confirmed Marketaux parser against LIVE response. Fixed JSE symbol suffix .JSE→.JO (Marketaux uses .JO, confirmed via entity search); per-ticker news now returns relevant sentiment-scored articles (SOL, NPN). General feed filtered to countries=za. Coverage patchy on free tier (MTN empty); noise remains in general — surfaced honestly.
- 2026-07-20 — Phase 5: indicators.py computes SMA/EMA/RSI/MACD/ATR in pure pandas (deterministic); fixed RSI flat-series=50 (not 100) and added neutral bands so a flat series scores HOLD not SELL (caught by tests).
- 2026-07-20 — Phase 5: technical/macro_regime/sentiment layers (each -1..1 with transparent sub-signals) + engine.py fusion (config weights, direction thresholds, ATR stop, risk-per-trade sizing, full rationale JSON) + performance.py (confidence from measured hit rate, None until Phase 6).
- 2026-07-20 — Phase 5: indicator-cache + signals repositories; compute_indicators & generate_signals jobs; nightly engine schedule (19:00) + JOBS entries.
- 2026-07-20 — Phase 5: GET /api/signals (filter date/direction/min_score), GET /api/signals/{id} (full rationale), POST /api/signals/{id}/status; frontend Signals page (ranked, filters, rationale, Acted/Dismissed) + nav + latest-signal on SecurityDetail.
- 2026-07-20 — Phase 5: verified live — ingested 1y prices, 6777 indicators, generated 3 signals (NPN/SOL/MTN HOLD with transparent rationale); endpoints incl. status update work; pytest 41 passing. Phase 5 complete (confidence blank until paper-trade history in Phase 6).
- 2026-07-20 — Phase 6: paper.py pure sim (stop/horizon exit, net P&L WITH brokerage+slippage costs per §10 honesty req); Costs config (BROKERAGE_PCT/SLIPPAGE_PCT). Deterministic unit tests.
- 2026-07-20 — Phase 6: paper_trades repository; generate_signals now opens a long paper trade from each actionable BUY (one per security); update_paper_trades job closes on stop/horizon and books net P&L; nightly schedule + JOBS.
- 2026-07-20 — Phase 6: performance.py extended with total P&L + equity curve; GET /api/paper/performance + /api/paper/trades; frontend Paper Performance page (Recharts equity curve, stat tiles, trades table, honest "edge not yet meaningful" banner) + nav.
- 2026-07-20 — Phase 6: verified live — update_paper_trades closed a seeded trade with correct cost-net P&L (gross 206200c − 32412.4c costs = 173787.6c); endpoints return honest empty state; pytest 48 passing. Phase 6 complete.
- 2026-07-20 — Phase 7: pure FIFO realised-gains tax logic (SA tax year 1 Mar–end Feb) in app/tax.py, incl. buy-fee base cost, sell-fee proceeds, oversold flagging; deterministic tests.
- 2026-07-20 — Phase 7: trades repository + schemas (price/fees entered & returned in Rand, stored in cents via rand_to_cents); GET/POST/DELETE /api/trades + GET /api/trades/tax-summary (link to signals supported).
- 2026-07-20 — Phase 7: frontend Journal page — log-trade form, trades table w/ delete, tax-year summary table + CSV export, tax disclaimer; nav + route.
- 2026-07-20 — Phase 7: verified live — logged BUY/SELL, tax-summary FY2026 proceeds R11,995 / base R10,005 / gain R1,990 (Rand↔cents round-trip correct); pytest 55 passing. Phase 7 complete.
- 2026-07-20 — Securities: EODHD_API_KEY added; confirmed live JSE listing shape (507 instruments: 258 Common Stock / 146 ETF / 103 FUND) — no Sector field, Currency="ZAC". Fixed seed to filter Common Stock only, normalise ZAC→ZAR, leave sector NULL. Seeded full universe → 259 securities (was 15) with real ISINs.
- 2026-07-20 — Sectors: EODHD fundamentals is paywalled on free tier (403) and Yahoo assetProfile needs an auth crumb (401) — no free API for sectors. Built curated jse_sectors.py map (well-known names only, no guessing) + enrich_sectors job. Applied → 53/259 have sectors incl. 14 Basic Materials + Sasol (Energy) which drive macro tilts; 206 small-caps remain NULL by design.
- 2026-07-20 — Phase 8: walk-forward backtester (signals/backtest.py) — technical-only (macro/sentiment excluded to avoid lookahead), one-trade-at-a-time, net of brokerage+slippage, OOS split; shared compute_trade_levels() with the engine. POST /api/backtest. Deterministic tests.
- 2026-07-20 — Phase 8: editable settings — app_config table (migration ac18b416ec12) + services/settings.py effective-settings (env + DB overrides); generate_signals/update_paper_trades now use effective settings; GET/PUT /api/settings.
- 2026-07-20 — Phase 8: frontend Backtest page (full vs OOS metrics, equity curve, lookahead/overfitting warnings) + Settings page (tunable weights/thresholds/risk/costs, weight-sum check, provider status) + nav.
- 2026-07-20 — Phase 8: verified live — backtest of NPN/SOL/MTN (OOS split 2026-04-01) returned 29 trades, and was NET NEGATIVE after costs (full win 45% / OOS win 20% / OOS P&L −R3,817) → HONEST headline: technical signal shows NO edge on this small sample. Settings round-trip works; pytest 64 passing. Phase 8 complete.
- 2026-07-20 — Phase 9: shared 429 exponential-backoff helper (backoff.py) applied to price + news fetches (refactored the old inline price backoff); documented per-provider free-tier ceilings + caching (DB upserts) + provider_calls logging as the rate-limit review.
- 2026-07-20 — Phase 9: GET /api/freshness (per-family last-ingest/latest-data/count + staleness) + app-wide staleness banner; React ErrorBoundary for graceful degradation.
- 2026-07-20 — Phase 9: README finalised — setup/run, ZAc cents convention, data sources, signal engine, paper/tax/backtest, and the rate-limit/caching/freshness operations review.
- 2026-07-20 — Phase 9: verified live — /api/freshness reports all families fresh (prices 753 / macro 2860 / news 11 / signals 12); pytest 68 passing; frontend build passes. Phase 9 complete — all phases 0–9 done.
- 2026-07-20 — Enhancements A–D: added SA Securities Transfer Tax (0.25% buy-side) to the cost model (paper + backtest); tunable via Settings.
- 2026-07-20 — A (Backtest v2): benchmark vs buy&hold + JSE Top 40 over the window; profit factor, expectancy, reward/risk, max-drawdown %; liquidity filter applied. Live: buy&hold +42.6% / Top40 +9.4% vs strategy losing (PF 0.65) — signal still has NO edge.
- 2026-07-20 — B: liquidity filter (avg daily traded value ≥ MIN_LIQUIDITY_ZAR) + cross-sectional momentum layer (WEIGHT_MOMENTUM, default 0 so behaviour unchanged until enabled) wired into generate_signals; momentum in rationale.
- 2026-07-20 — C: portfolio risk controls — MAX_OPEN_POSITIONS + MAX_POSITIONS_PER_SECTOR caps when opening paper trades; trailing stop (TRAILING_STOP_PCT) in the shared evaluate_exit (paper + backtest).
- 2026-07-20 — D: SENS announcements — sens_announcements table (migration 6672da5982d8), configurable RSS provider (SENS_RSS_URL), headline→security matching, ingest_sens job (hourly), GET /api/sens, SecurityDetail feed. NOTE: no free authoritative SENS feed found (Moneyweb RSS returns empty, others are HTML/paywalled) — pipeline ingests whatever a configured feed provides; currently empty, surfaced honestly.
- 2026-07-20 — A–D: dark theme applied app-wide (CSS variables); pytest 79 passing; frontend build passes; live smoke of backtest/settings/sens OK. Confidence/edge still unproven — see benchmark.
- 2026-07-21 — Ingested 2y daily prices for 52 liquid large-caps (BHP delisted from .JO, excluded); 25,896 bars, 233,091 indicators.
- 2026-07-21 — Built cross-sectional momentum PORTFOLIO backtest (walk-forward, no lookahead, net of costs incl STT): equal-weight top-K by trailing return, periodic rebalance; POST /api/backtest/momentum; Backtest page strategy toggle. Unit-tested. pytest 81 passing.
- 2026-07-21 — FINDING (2y, 52 names, net of costs): technical signal still loses (1020 trades, PF 0.68) — no edge, large sample confirms. Momentum top10/21d = +38.5% (ann 21.6%, Sharpe 0.96, maxDD -14.2%) BEAT buy&hold +30.9% (Top40 +9.4%). First config with an apparent edge. CAVEATS: survivorship bias (today's survivors), tiny sample (20 periods), single bull-market window, mild config overfit, SA income-tax drag — promising, NOT proven; not for real money yet.
- 2026-07-21 — Ingested ~10y prices (125,126 bars, 1.13M indicators, 52 names) + added out-of-sample split to the momentum backtest (POST /api/backtest/momentum split_date; full vs OOS metrics; Backtest UI updated). pytest 82 passing.
- 2026-07-21 — Pine Script export: GET /api/pinescript generates a TradingView v5 strategy mirroring the app's TECHNICAL backtest (same sub-signals/weights/thresholds/ATR-stop/horizon, cost-aware) from effective settings; new "Pine" page (code + copy + params + instructions). Single-symbol only (macro/sentiment/momentum excluded); flagged as a directional cross-check, not a decimal match.
- 2026-07-21 — Drill-down: new Securities search/browse page (open ANY of the 259 by code/name) + nav; SecurityDetail gains a time-range selector (1M–Max), key stats (last/period change/high/low), SMA20/50 chart overlays + volume pane, and auto-fetches prices on first open if none stored.
- 2026-07-21 — DECISIVE FINDING (10y, 2016–2026, net of costs): the promising 2y momentum result did NOT survive. buy&hold avg +73%. Momentum top10/21d = +50% over 10y (ann 4.3%, Sharpe 0.32, maxDD −40%); OOS 2021+ ann 7.8%, Sharpe 0.50 — badly lags buy&hold. Results are wildly parameter-sensitive (top10/42d +244% vs top5/21d +56%), a classic OVERFITTING red flag. Conclusion: no robust edge demonstrated; buy&hold remains the benchmark to beat; survivorship bias makes even these figures optimistic. The OOS + long-window test did its job — it disproved the 2y result.
