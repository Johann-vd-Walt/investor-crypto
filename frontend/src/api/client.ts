// Typed API client for the Crypto Swing-Trading backend.
// Uses same-origin relative /api paths (proxied to FastAPI in dev via vite.config.ts).

const API_BASE = import.meta.env.VITE_API_BASE ?? ''
const TOKEN_KEY = 'cst_token'

export const getToken = () => localStorage.getItem(TOKEN_KEY) ?? ''
export const setToken = (t: string) => localStorage.setItem(TOKEN_KEY, t)
export const clearToken = () => localStorage.removeItem(TOKEN_KEY)

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
    this.name = 'ApiError'
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const token = getToken()
  const resp = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...init?.headers,
    },
  })
  if (resp.status === 401 && !path.startsWith('/api/auth/')) {
    // Session missing/expired — drop the token and ask the app to show login.
    clearToken()
    window.dispatchEvent(new Event('auth-required'))
    throw new ApiError(401, 'Authentication required')
  }
  if (!resp.ok) {
    let detail = resp.statusText
    try {
      const body = await resp.json()
      detail = body.detail ?? detail
    } catch {
      // non-JSON error body; keep statusText
    }
    throw new ApiError(resp.status, detail)
  }
  if (resp.status === 204) return undefined as T
  return (await resp.json()) as T
}

// --- Types (mirror the backend Pydantic schemas) ---

export interface Security {
  id: number
  ticker: string
  isin: string | null
  name: string
  sector: string | null
  currency: string
  is_active: boolean
  created_at: string
  updated_at: string
}

export interface SecurityListResponse {
  items: Security[]
  total: number
  limit: number
  offset: number
}

export interface WatchlistItem {
  id: number
  added_at: string
  notes: string | null
  security: Security
}

export interface PriceBar {
  bar_datetime: string
  open: number
  high: number
  low: number
  close: number
  adj_close: number | null
  volume: number | null
}

export interface PriceSeries {
  ticker: string
  timeframe: string
  currency: string
  unit: string
  as_of: string | null
  is_delayed: boolean
  source: string | null
  bars: PriceBar[]
}

export interface MacroSnapshotItem {
  series_code: string
  label: string
  available: boolean
  value: number | null
  unit: string | null
  as_of: string | null
  source: string | null
  note: string | null
}

export interface MacroSnapshotResponse {
  items: MacroSnapshotItem[]
}

export interface MacroObservation {
  observation_date: string
  value: number
  unit: string | null
  source: string | null
}

export interface MacroSeriesResponse {
  series_code: string
  label: string
  unit: string | null
  source: string | null
  observations: MacroObservation[]
}

export interface NewsArticle {
  id: number
  source: string
  url: string
  title: string
  snippet: string | null
  published_at: string | null
  language: string | null
  entity_symbol: string | null
  sentiment: number | null
  relevance: number | null
}

export interface NewsListResponse {
  ticker: string | null
  count: number
  articles: NewsArticle[]
}

export type SignalDirection = 'BUY' | 'SELL' | 'HOLD'
export type SignalStatus = 'OPEN' | 'ACTED' | 'EXPIRED' | 'DISMISSED'

export interface Signal {
  id: number
  security_id: number
  ticker: string
  generated_at: string
  horizon_days: number
  direction: SignalDirection
  score: number
  confidence: number | null
  technical_score: number | null
  macro_score: number | null
  sentiment_score: number | null
  suggested_entry: number | null
  suggested_stop: number | null
  suggested_size: number | null
  rationale: Record<string, unknown> | null
  status: SignalStatus
}

export interface SignalListResponse {
  items: Signal[]
  total: number
  limit: number
  offset: number
}

export interface PaperTrade {
  id: number
  security_id: number
  ticker: string
  entry_datetime: string
  entry_price: number
  quantity: number
  stop_price: number | null
  exit_datetime: string | null
  exit_price: number | null
  pnl: number | null
  unrealized_pnl: number | null
  status: 'OPEN' | 'CLOSED'
}

export interface EquityPoint {
  date: string
  cumulative_pnl: number
}

export interface PaperPerformance {
  sample_size: number
  wins: number
  min_sample: number
  has_edge_data: boolean
  win_rate: number | null
  avg_return_pct: number | null
  total_pnl: number
  equity_curve: EquityPoint[]
}

export type TradeSide = 'BUY' | 'SELL'

export interface Trade {
  id: number
  security_id: number
  ticker: string
  side: TradeSide
  quantity: number
  price: number
  fees: number
  trade_datetime: string
  linked_signal_id: number | null
  rationale: string | null
  created_at: string
}

export interface TradeListResponse {
  items: Trade[]
  total: number
  limit: number
  offset: number
}

export interface Disposal {
  ticker: string
  sell_datetime: string
  quantity: number
  proceeds: number
  base_cost: number
  gain: number
  unmatched_quantity: number
}

export interface TaxSummary {
  tax_year: number
  period_start: string
  period_end: string
  disposals: Disposal[]
  total_proceeds: number
  total_base_cost: number
  total_realised_gain: number
  disclaimer: string
}

export interface NewTrade {
  ticker: string
  side: TradeSide
  quantity: number
  price: number
  fees: number
  trade_datetime: string
  linked_signal_id?: number | null
  rationale?: string | null
}

export interface BacktestMetrics {
  trades: number
  wins: number
  win_rate: number | null
  avg_return_pct: number | null
  total_pnl: number
  avg_hold_days: number | null
  max_drawdown: number
  max_drawdown_pct: number | null
  profit_factor: number | null
  expectancy: number
  reward_risk: number | null
  sharpe: number | null
  psr: number | null
  deflated_sharpe: number | null
  trials: number
  robustness_note: string
}

export interface Benchmark {
  window_start: string | null
  window_end: string | null
  buy_hold_avg_pct: number | null
  btc_pct: number | null
}

export interface BacktestResponse {
  tickers_tested: number
  split_date: string | null
  full: BacktestMetrics
  out_of_sample: BacktestMetrics | null
  benchmark: Benchmark
  equity_curve: { date: string; cumulative_pnl: number }[]
  sample_trades: {
    ticker: string
    entry_datetime: string
    exit_datetime: string | null
    entry_price: number
    exit_price: number | null
    quantity: number
    pnl: number | null
    return_pct: number | null
    reason: string | null
  }[]
  scope_note: string
  disclaimer: string
}

export interface MomentumMetrics {
  n_rebalances: number
  total_return_pct: number | null
  annualised_return_pct: number | null
  sharpe: number | null
  max_drawdown_pct: number | null
  avg_holdings: number | null
  win_rate_periods: number | null
}

export interface MomentumResponse {
  tickers_tested: number
  top_k: number
  rebalance_days: number
  split_date: string | null
  full: MomentumMetrics
  out_of_sample: MomentumMetrics | null
  benchmark: Benchmark
  latest_holdings: string[]
  equity_curve: { date: string; equity: number }[]
  scope_note: string
  disclaimer: string
}

export interface AppSettings {
  weight_technical: number
  weight_macro: number
  weight_sentiment: number
  weight_momentum: number
  buy_threshold: number
  sell_threshold: number
  default_horizon_days: number
  account_size: number
  risk_per_trade_pct: number
  atr_stop_multiple: number
  brokerage_pct: number
  slippage_pct: number
  stt_pct: number
  min_liquidity_zar: number
  liquidity_lookback_days: number
  momentum_lookback_days: number
  momentum_skip_days: number
  max_open_positions: number
  max_positions_per_sector: number
  trailing_stop_pct: number
  weight_sum: number
  weights_ok: boolean
  overrides: Record<string, unknown>
  providers: Record<string, boolean>
}

export interface SensItem {
  id: number
  security_id: number | null
  ticker: string | null
  source: string
  url: string
  headline: string
  summary: string | null
  category: string | null
  published_at: string | null
}

export interface SensListResponse {
  ticker: string | null
  count: number
  items: SensItem[]
}

export interface FreshnessFamily {
  name: string
  last_ingest: string | null
  latest_data: string | null
  count: number
  stale: boolean
}

export interface FreshnessResponse {
  as_of: string
  families: FreshnessFamily[]
  overall_stale: boolean
}

export interface HealthResponse {
  status: 'ok' | 'degraded'
  app_env: string
  database: { connected: boolean; error: string | null }
  providers: Record<string, boolean>
}

export type AuthEventType = 'success' | 'failed' | 'locked'

export interface AuthEvent {
  id: number
  created_at: string
  event: AuthEventType
  ip: string | null
  user_agent: string | null
}

export interface AuthSummary {
  window_hours: number
  success: number
  failed: number
  locked: number
  distinct_failed_ips: number
}

export interface AccessLogResponse {
  summary: AuthSummary
  events: AuthEvent[]
}

export type PositioningTone = 'bull' | 'bear' | 'warn' | 'neutral'

export interface PositioningSignal {
  metric: string
  label: string
  detail: string
  value: number | null
  percentile: number | null
  tone: PositioningTone
  sample: number
}

export interface PositioningSnapshot {
  ticker: string
  name: string
  as_of: string | null
  available: boolean
  signals: PositioningSignal[]
  note: string
}

export interface PositioningListResponse {
  count: number
  items: PositioningSnapshot[]
}

export interface CoinConsensus {
  ticker: string | null
  inst: string
  longs: number
  shorts: number
  traders: number
  net_bias: number
  lean: 'long' | 'short' | 'split'
}

export interface ConsensusResponse {
  source: string
  traders_sampled: number
  as_of_cache_age_s: number
  available: boolean
  items: CoinConsensus[]
  caveat: string
}

// --- Endpoints ---

export const api = {
  health: () => request<HealthResponse>('/api/health'),
  getFreshness: () => request<FreshnessResponse>('/api/freshness'),

  getAuthStatus: () => request<{ enabled: boolean; authenticated: boolean }>('/api/auth/status'),
  login: (code: string) =>
    request<{ token: string; expires_in: number }>('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify({ code }),
    }),

  listSecurities: (params: { query?: string; sector?: string; limit?: number } = {}) => {
    const qs = new URLSearchParams()
    if (params.query) qs.set('query', params.query)
    if (params.sector) qs.set('sector', params.sector)
    if (params.limit) qs.set('limit', String(params.limit))
    const suffix = qs.toString() ? `?${qs.toString()}` : ''
    return request<SecurityListResponse>(`/api/securities${suffix}`)
  },

  listWatchlist: () => request<WatchlistItem[]>('/api/watchlist'),

  addWatchlist: (ticker: string, notes?: string) =>
    request<WatchlistItem>('/api/watchlist', {
      method: 'POST',
      body: JSON.stringify({ ticker, notes: notes || undefined }),
    }),

  removeWatchlist: (id: number) =>
    request<void>(`/api/watchlist/${id}`, { method: 'DELETE' }),

  getSecurity: (ticker: string) =>
    request<Security>(`/api/securities/${encodeURIComponent(ticker)}`),

  getPrices: (ticker: string, timeframe = '1d') =>
    request<PriceSeries>(
      `/api/prices/${encodeURIComponent(ticker)}?timeframe=${timeframe}`,
    ),

  getMacroSnapshot: () => request<MacroSnapshotResponse>('/api/macro'),
  getMacroSeries: (code: string) =>
    request<MacroSeriesResponse>(`/api/macro/${encodeURIComponent(code)}`),

  getTickerNews: (ticker: string, limit = 20) =>
    request<NewsListResponse>(
      `/api/news?ticker=${encodeURIComponent(ticker)}&limit=${limit}`,
    ),

  getGeneralNews: (limit = 20) =>
    request<NewsListResponse>(`/api/news/general?limit=${limit}`),

  listSignals: (params: { direction?: SignalDirection; minScore?: number } = {}) => {
    const qs = new URLSearchParams()
    if (params.direction) qs.set('direction', params.direction)
    if (params.minScore !== undefined) qs.set('min_score', String(params.minScore))
    const suffix = qs.toString() ? `?${qs.toString()}` : ''
    return request<SignalListResponse>(`/api/signals${suffix}`)
  },

  setSignalStatus: (id: number, status: SignalStatus) =>
    request<Signal>(`/api/signals/${id}/status`, {
      method: 'POST',
      body: JSON.stringify({ status }),
    }),

  getPaperTrades: () => request<PaperTrade[]>('/api/paper/trades'),
  getPaperPerformance: () => request<PaperPerformance>('/api/paper/performance'),

  listTrades: () => request<TradeListResponse>('/api/trades'),
  createTrade: (t: NewTrade) =>
    request<Trade>('/api/trades', { method: 'POST', body: JSON.stringify(t) }),
  deleteTrade: (id: number) =>
    request<void>(`/api/trades/${id}`, { method: 'DELETE' }),
  getTaxSummary: (taxYear?: number) =>
    request<TaxSummary>(`/api/trades/tax-summary${taxYear ? `?tax_year=${taxYear}` : ''}`),

  runBacktest: (body: { tickers?: string[]; split_date?: string; trials?: number; overrides?: Record<string, unknown> }) =>
    request<BacktestResponse>('/api/backtest', { method: 'POST', body: JSON.stringify(body) }),

  runMomentumBacktest: (body: { tickers?: string[]; top_k?: number; rebalance_days?: number; split_date?: string }) =>
    request<MomentumResponse>('/api/backtest/momentum', { method: 'POST', body: JSON.stringify(body) }),

  getPineScript: () =>
    request<{ pine: string; params: Record<string, number>; notes: string[] }>('/api/pinescript'),

  getSettings: () => request<AppSettings>('/api/settings'),
  updateSettings: (overrides: Record<string, unknown>) =>
    request<AppSettings>('/api/settings', { method: 'PUT', body: JSON.stringify({ overrides }) }),

  getSens: (ticker?: string, limit = 20) => {
    const qs = new URLSearchParams()
    if (ticker) qs.set('ticker', ticker)
    qs.set('limit', String(limit))
    return request<SensListResponse>(`/api/sens?${qs.toString()}`)
  },

  getAccessLog: (limit = 200) =>
    request<AccessLogResponse>(`/api/security/access-log?limit=${limit}`),

  getPositioning: () => request<PositioningListResponse>('/api/positioning'),
  getPositioningFor: (ticker: string) =>
    request<PositioningSnapshot>(`/api/positioning/${encodeURIComponent(ticker)}`),

  getConsensus: () => request<ConsensusResponse>('/api/consensus'),

  // Dev-only manual job trigger (APP_ENV=development).
  runJob: (job_name: string, params: Record<string, unknown> = {}) =>
    request<{ job_name: string; result: unknown }>('/api/admin/run-job', {
      method: 'POST',
      body: JSON.stringify({ job_name, params }),
    }),
}
