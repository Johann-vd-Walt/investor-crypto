# Crypto Swing-Trading Decision-Support App

A **personal, decision-support-only** desktop web app for short-hold swing
trades on **crypto assets** (Bitcoin, Ethereum and major altcoins). It ingests
daily price data from Binance, the crypto Fear & Greed index, and optional news,
then produces **explainable** buy/sell/hold signals, paper-trades them, and
backtests strategies honestly.

> **It does not place trades, connect to your exchange/wallet, or advise anyone
> but the owner.** Crypto is highly volatile — you can lose everything. Signals
> are probabilistic estimates and are frequently wrong.

> **Reworked from a JSE-equities app to crypto (2026-08-13).** The architecture
> (signal engine, backtester, paper trading, journal/tax, settings) was reused;
> the data layer, units, market-regime and branding were rebuilt for crypto.
> Some deeper docs below still describe the original JSE phases — treat the
> crypto notes here and the top of `PROJECT_SPEC.md`'s progress log as current.

Stack: **Python 3.12+ · FastAPI · SQLAlchemy 2 · MySQL 8 · React 18 + Vite + TS**

## Login (optional TOTP gate — Google Authenticator)

A single global TOTP code gates the whole app (no users/roles). It's **off by
default** so you can't lock yourself out. To turn it on:

```bash
cd backend
.\.venv\Scripts\python.exe -m app.auth_setup   # prints a QR + secret, writes TOTP_SECRET to .env
```

Scan the QR with Google Authenticator (or "Enter a setup key" with the printed
secret), then restart the backend. You'll now need the 6-digit code to enter.
Enforced **server-side**: every `/api/*` route (except `/api/auth/*` and
`/api/health`) requires a valid session token; the frontend shows a lock screen.
To turn it off again, blank `TOTP_SECRET` in `.env`. Keep the secret private —
anyone with it can log in.

## Recommended platforms

- **Market data (used by the app): Binance public API** — free, no key, deep
  history (BTC since 2017). Endpoint `data-api.binance.vision` (no geo issues).
- **Your wallet / API key (for actually trading): VALR** — South-African,
  FSCA-registered, ZAR + USDT pairs, strong API, low fees. **Luno** is a simpler
  SA alternative. **The app never needs your key** — it uses public data and is
  decision-support only. You place orders yourself on the exchange.

---

## Units convention (READ THIS)

Crypto prices are stored and returned in the pair's **quote currency (USDT)** at
**native precision** — there is no cents convention. `DECIMAL(24,10)` columns
hold everything from BTC (~$63,000) to sub-cent alts. `account_size` and all
P&L are in USDT. **Money is `DECIMAL`, never `float`** in storage/arithmetic;
only the JSON presentation layer emits numbers. `/api/prices/*` returns
`unit: "usdt"`, `as_of`, and `is_delayed`.

## Market regime & sentiment (crypto)

The JSE macro layer (oil/gold/rand/indices) is replaced by:
- **Market regime** — driven by the **BTC trend** (crypto is BTC-correlated).
- **Sentiment** — the **crypto Fear & Greed index** (alternative.me), mapped to
  −1..1 (greed positive). Both are market-wide.

## Signal engine (Phase 5)

Three transparent layers, each scoring −1..1, fused with the configurable
weights (`WEIGHT_TECHNICAL/MACRO/SENTIMENT`, must sum to 1.0):

- **Technical** ([technical.py](backend/app/signals/technical.py)) — SMA/EMA
  trend, RSI, MACD, volume-confirmed breakout, ATR for stops.
- **Macro regime** ([macro_regime.py](backend/app/signals/macro_regime.py)) —
  market-wide score + named regime (e.g. "weak rand, rising gold") from
  USD/ZAR, gold, oil, ALSI; tilts sectors.
- **Sentiment** ([sentiment.py](backend/app/signals/sentiment.py)) — recent news
  sentiment weighted by coverage.

[engine.py](backend/app/signals/engine.py) fuses them, sets direction from
thresholds (`BUY_THRESHOLD`/`SELL_THRESHOLD`), computes an ATR-based stop and a
risk-per-trade position size (`ACCOUNT_SIZE`, `RISK_PER_TRADE_PCT`,
`ATR_STOP_MULTIPLE`), and writes a full **rationale JSON** listing every
sub-signal that fired — no hidden confidence (§8). Indicators are computed
directly in pandas (no `pandas-ta`; see the requirements note).

**Confidence** comes only from the engine's *measured* hit rate over closed
paper trades ([performance.py](backend/app/signals/performance.py)); until Phase
6 produces that history it is shown as blank, never invented.

Jobs: `compute_indicators` (cache) then `generate_signals` (nightly 19:00, or
via `run-job`). A security needs **≥50 daily bars** to be scored.

## Enhancements A–D (post-Phase-9)

- **A — Backtest v2:** benchmarks the strategy against **buy-and-hold** (avg of
  tested names) and the **JSE Top 40** over the same window, and adds profit
  factor, expectancy, reward/risk and max-drawdown %. **SA Securities Transfer
  Tax (0.25%, buy-side)** is now in the cost model (paper + backtest). Read the
  benchmark: if buy-and-hold beats the strategy, the signal isn't adding value.
- **B — Liquidity + momentum:** securities below `MIN_LIQUIDITY_ZAR` average
  daily traded value are skipped (untradeable thin names). A **cross-sectional
  momentum** layer (`WEIGHT_MOMENTUM`, default 0 = off) ranks the liquid
  universe by relative strength and feeds the fused score.
- **C — Portfolio risk controls:** `MAX_OPEN_POSITIONS` and
  `MAX_POSITIONS_PER_SECTOR` cap concurrent paper positions; `TRAILING_STOP_PCT`
  enables a trailing stop in the shared exit logic (paper + backtest).
- **D — SENS announcements:** `GET /api/sens`, a Security-detail feed, and an
  hourly `ingest_sens` job reading a configurable RSS feed (`SENS_RSS_URL`).
  **No free authoritative SENS feed was found** (the JSE's is licensed; free
  RSS/HTML sources are empty or scraping-only), so this ingests whatever a
  configured feed provides and honestly shows nothing when the feed is empty.

All of the above are tunable on the **Settings** page. The app is **dark-themed**.

### Cross-sectional momentum backtest (`POST /api/backtest/momentum`)

A proper portfolio backtest: every `rebalance_days`, hold the **top-K liquid
names by trailing momentum** (equal weight), walk-forward with no lookahead, net
of round-trip costs incl. STT. Selectable on the Backtest page.

Supports an **out-of-sample split** (`split_date`) — full vs held-out metrics.

**What the validation actually showed (be clear-eyed):** on a 2-year window
momentum (top-10, monthly) looked great — +38.5% vs +30.9% buy-and-hold. But
extended to **~10 years (2016–2026)** it **fell apart**: buy-and-hold averaged
**+73%**, while momentum (top-10, monthly) made only **+50% (≈4.3%/yr, Sharpe
0.32, −40% drawdown)**, similar out-of-sample. Worse, results swing wildly with
the rebalance parameter (top-10/42-day showed +244%, top-5/monthly +56%) — a
textbook **overfitting** red flag. The technical signal keeps losing throughout.

**Conclusion: no robust edge has been demonstrated. Buy-and-hold is still the
benchmark to beat, and survivorship bias makes even these figures optimistic.**
The out-of-sample + long-window tests did their job — they disproved a
result that looked promising on a short window. That is the app working
correctly: it stops you trading a mirage.

## Operations: rate limits, caching & freshness (Phase 9)

**Rate-limit & caching review (Guardrail 2.6):**
- Every external call is logged to `provider_calls` (provider, endpoint, status,
  rows, note).
- All fetched data is cached durably in MySQL (`price_bars`, `macro_series`,
  `indicator_values`, `news_articles`) and upserts are idempotent, so re-running
  a job doesn't duplicate rows.
- HTTP **429** is retried with exponential backoff via a shared helper
  ([backoff.py](backend/app/ingestion/backoff.py)) on both price and news
  fetches; Alpha Vantage throttle responses raise a typed error and are skipped.
- Batching: news fetches all watchlist symbols in one call; ingest jobs isolate
  per-item failures so one bad symbol never aborts a run.
- Known free-tier ceilings: **Alpha Vantage ~25/day** (used for WTI/CPI only, ~2
  calls/run), **EODHD 20/day + EOD-only** (listing seed + prices; fundamentals
  paywalled), **Marketaux ~100/day**, **Yahoo** unofficial (be polite).

**Data freshness (Guardrail 2.7):** `GET /api/freshness` reports, per family
(prices/macro/news/signals), the last ingest time, latest data, row count and a
`stale` flag. A banner at the top of the app warns when any populated family is
stale. Prices always carry `as_of` + a **DELAYED** badge; macro/signals carry
`as_of`/`generated_at`. Stale data is never served as fresh.

**Graceful degradation:** the React app is wrapped in an ErrorBoundary (a page
render error shows a message + retry, not a white screen), every data view has
explicit loading/error/empty states, and the backend starts and `/api/health`
responds even with the DB down or provider keys missing.

## Backtesting & settings (Phase 8)

`POST /api/backtest` runs a **walk-forward** backtest: at each bar the technical
signal uses only past data, and the trade is simulated forward — **no
lookahead** — with brokerage + slippage applied. It reports full-sample and
**out-of-sample** metrics (split by date) plus an equity curve and max drawdown.

> **Scope (honest):** the backtest covers the **technical** signal only. Macro
> regime and news sentiment are excluded because scoring past dates with today's
> macro/news values would be lookahead. Read the **out-of-sample** column, and
> beware overfitting when tuning settings against the same data.

**Settings** (`GET`/`PUT /api/settings`, Settings page) persist tunable
overrides (weights, thresholds, risk-per-trade, account size, ATR multiple,
costs) in the `app_config` table. The engine and backtester use *effective*
settings (env defaults + overrides) with no restart. `.env` remains the default.

## Trade journal & tax (Phase 7)

Log **real** trades manually (`POST /api/trades`) — prices/fees entered in Rand,
stored in cents. `GET /api/trades` lists the journal; trades can link to a
signal. `GET /api/trades/tax-summary?tax_year=YYYY` produces a **record-keeping**
summary of realised disposals for the SA tax year (1 March–end February),
FIFO-matched, with buy fees in base cost and sell fees netted off proceeds. The
Journal page can export it to CSV.

> **Not tax advice.** Short-term frequent trading may be taxed as income rather
> than capital gains in South Africa — confirm with a registered tax
> practitioner. The `trades` (real) table is kept separate from `paper_trades`
> (simulated).

## Paper trading & performance (Phase 6)

`generate_signals` opens a **long paper trade** from each actionable BUY signal
(sized by the risk rule, one open trade per security). `update_paper_trades`
(nightly, or via `run-job`) closes each on a **stop hit or the signal horizon**,
whichever comes first, and books **P&L net of realistic costs** — brokerage +
slippage (`BROKERAGE_PCT`, `SLIPPAGE_PCT`). Cost-free simulation is deliberately
avoided (§10): it would overstate the edge.

- `GET /api/paper/trades` — all paper trades (net P&L closed; unrealized for open)
- `GET /api/paper/performance` — win rate, avg return, total P&L, equity curve

**Honesty:** win rate / confidence are withheld until at least `MIN_SAMPLE`
(10) closed trades exist — before that the Paper page shows an explicit "edge
not yet meaningful" banner and confidence stays blank. This is measured
performance, not a promise; it is still **not** an out-of-sample backtest
(Phase 8).

## Macro / commodity / FX data sources (Phase 3)

Provider choices reflect what actually works on the free tiers (probed against
live responses, 2026-07-20). Response shapes were confirmed, not assumed (§8).

| Series | Source | Cadence | Notes |
|---|---|---|---|
| WTI, US_CPI | Alpha Vantage | monthly | free tier ~25 req/day, ~1/sec — used sparingly |
| BRENT | OilPriceAPI | current spot | latest spot price |
| USD/ZAR, GOLD | Yahoo (`USDZAR=X`, `GC=F`) | daily | keyless |
| JSE All-Share, Top 40 | Yahoo (`^J203.JO`, `^J200.JO`) | daily | keyless |
| **SA repo rate** | **none yet** | — | **no free source wired; needs SARB scraping. Surfaced as "unavailable" in the snapshot rather than faked.** |

Alpha Vantage forex was the spec's first choice for FX, but its free tier
(~25 calls/day) is impractical for daily ingestion — USD/ZAR is sourced from
Yahoo instead. Macro values are stored in **native units** (USD, ZAR/USD, index
points); the ZAc-cents convention applies only to JSE *share* prices.

## News & sentiment (Phase 4)

News comes from **Marketaux** (`GET /v1/news/all`), deduplicated by
`url_hash = sha256(url)`. Each article's per-entity `sentiment_score` (−1..1
scale, §8) is stored in `news_sentiment`, linked to a security when the entity
symbol matches a known ticker (`NPN.JSE` → `NPN`); general market news is stored
with a `security_id`-NULL row.

- `GET /api/news?ticker=NPN` — per-security feed with sentiment
- `GET /api/news/general` — general market news
- `ingest_news` runs hourly (and via `run-job`).

**Marketaux JSE symbols use the `.JO` suffix** (confirmed via entity search —
e.g. `SOL.JO`, country `za`), the same as Yahoo. Verified live 2026-07-20:
per-ticker queries return relevant, sentiment-scored articles (Sasol, Naspers).
Coverage on the free tier is patchy (e.g. MTN returned nothing), and the
general (`countries=za`) feed still includes some off-topic items — free-tier
limitations, surfaced as-is rather than hidden.

### Running the news job

```bash
# from the CLI (no server needed) — reads .env fresh:
cd backend
.\.venv\Scripts\python.exe -c "from app.ingestion.jobs import ingest_news; print(ingest_news())"

# or via the dev API (backend running, APP_ENV=development):
#   POST /api/admin/run-job  {"job_name":"ingest_news"}
#   POST /api/admin/run-job  {"job_name":"ingest_news","params":{"tickers":["SOL","NPN"]}}

# or from the UI: open a stock (e.g. /security/SOL) and click "Refresh news".
# It also runs automatically every hour while the backend is up.
```

> After editing `.env`, **restart the backend** — settings are read once at
> startup (`get_settings()` is cached), so a running server won't see a new key
> until it restarts.

## Price data provider

Owner decision (2026-07-20): **Yahoo Finance (`{TICKER}.JO`) is the primary
price source** for prototyping — free, no key, delayed/EOD. Set
`PRICE_PROVIDER=yahoo` (default) or `PRICE_PROVIDER=eodhd` (requires
`EODHD_API_KEY`). The EODHD provider's endpoint and JSE price **unit** are
UNVERIFIED (no key was available during development) — confirm both against a
known close before relying on it. Yahoo is unofficial and best-effort; treat it
as prototype-grade.

---

## Project layout

```
backend/    FastAPI app, SQLAlchemy models, providers, ingestion, signal engine
frontend/   React 18 + Vite + TypeScript dashboard
PROJECT_SPEC.md   The authoritative spec — build one task at a time, top-to-bottom
```

---

## Setup

### Prerequisites
- Python 3.12+ (verified working on 3.14)
- Node 18+ (verified on Node 24)
- MySQL 8.x running locally

### Backend

```bash
cd backend
python -m venv .venv
# Windows PowerShell:
.\.venv\Scripts\Activate.ps1
# macOS/Linux:
# source .venv/bin/activate

pip install -r requirements.txt

# Configure secrets (NEVER commit .env — Guardrail 2.1)
cp .env.example .env        # Windows: Copy-Item .env.example .env
# edit .env: set DATABASE_URL and any provider API keys you have

# Run the API (auto-reload for dev)
uvicorn app.main:app --reload
```

- API docs (OpenAPI/Swagger): http://localhost:8000/docs
- Health check: http://localhost:8000/api/health

The app **starts cleanly even with missing provider keys or an unreachable
database** — it logs warnings and `/api/health` reports `"degraded"` rather
than crashing.

#### Database migrations (Alembic)

```bash
cd backend
alembic upgrade head          # apply migrations
alembic revision --autogenerate -m "message"   # generate a new migration (Phase 1+)
```

Alembic reads `DATABASE_URL` from your `.env` (wired in `app/migrations/env.py`).

#### Tests

```bash
cd backend
pytest
```

### Frontend

```bash
cd frontend
npm install
npm run dev        # dev server on http://localhost:5173
npm run build      # production build
```

CORS on the backend allows the Vite dev origin (`FRONTEND_ORIGIN` in `.env`,
default `http://localhost:5173`).

---

## Build status

See the **Progress log** at the bottom of `PROJECT_SPEC.md`. Built one task at
a time through the phased plan in §13.
