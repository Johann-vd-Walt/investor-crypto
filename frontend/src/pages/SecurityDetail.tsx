import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useParams } from 'react-router-dom'
import { api, type PriceBar } from '../api/client'
import CandlestickChart from '../components/CandlestickChart'
import DelayedBadge from '../components/DelayedBadge'
import DirectionBadge from '../components/DirectionBadge'
import Explainer from '../components/Explainer'

const RANGES: { label: string; days: number | null }[] = [
  { label: '1M', days: 30 },
  { label: '3M', days: 90 },
  { label: '6M', days: 180 },
  { label: '1Y', days: 365 },
  { label: '2Y', days: 730 },
  { label: 'Max', days: null },
]

function sliceByRange(bars: PriceBar[], days: number | null): PriceBar[] {
  if (days === null || bars.length === 0) return bars
  const cutoff = Date.parse(bars[bars.length - 1].bar_datetime) - days * 86400_000
  return bars.filter((b) => Date.parse(b.bar_datetime) >= cutoff)
}

export default function SecurityDetail() {
  const { ticker = '' } = useParams()
  const qc = useQueryClient()
  const [range, setRange] = useState<number | null>(365)

  const security = useQuery({
    queryKey: ['security', ticker],
    queryFn: () => api.getSecurity(ticker),
    enabled: !!ticker,
  })

  const prices = useQuery({
    queryKey: ['prices', ticker],
    queryFn: () => api.getPrices(ticker),
    enabled: !!ticker,
  })

  const refresh = useMutation({
    mutationFn: () => api.runJob('ingest_daily_prices', { tickers: [ticker] }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['prices', ticker] }),
  })

  // Seamless drill-down: if a security has no stored prices yet, fetch once.
  const [autoTried, setAutoTried] = useState(false)
  useEffect(() => setAutoTried(false), [ticker])
  useEffect(() => {
    if (
      prices.isSuccess && prices.data.bars.length === 0 &&
      !autoTried && !refresh.isPending
    ) {
      setAutoTried(true)
      refresh.mutate()
    }
  }, [prices.isSuccess, prices.data, autoTried, refresh])

  const sens = useQuery({ queryKey: ['sens', ticker], queryFn: () => api.getSens(ticker), enabled: !!ticker })
  const signals = useQuery({ queryKey: ['signals-for', ticker], queryFn: () => api.listSignals(), enabled: !!ticker })
  const latestSignal = signals.data?.items.find((s) => s.ticker === ticker)

  const refreshNews = useMutation({
    mutationFn: () => api.runJob('ingest_sens'),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['sens', ticker] }),
  })

  const allBars = prices.data?.bars ?? []
  const bars = useMemo(() => sliceByRange(allBars, range), [allBars, range])

  const stats = useMemo(() => {
    if (bars.length === 0) return null
    const closes = bars.map((b) => b.close)
    const highs = bars.map((b) => b.high)
    const lows = bars.map((b) => b.low)
    const first = closes[0]
    const last = closes[closes.length - 1]
    return {
      last,
      hi: Math.max(...highs),
      lo: Math.min(...lows),
      changePct: first ? ((last - first) / first) * 100 : null,
      bars: bars.length,
    }
  }, [bars])

  const rands = (n: number) => {
    const abs = Math.abs(n)
    const dp = abs >= 1 ? 2 : abs >= 0.01 ? 4 : 8
    return `$${n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: dp })}`
  }

  return (
    <section>
      <p><Link to="/securities">← Securities</Link>{'  '}<Link to="/watchlist">Watchlist</Link></p>

      <div className="detail-head">
        <div>
          <h1>{ticker}</h1>
          {security.data && (
            <p className="muted">
              {security.data.name}
              {security.data.sector ? ` · ${security.data.sector}` : ''}
              {security.data.isin ? ` · ${security.data.isin}` : ''}
            </p>
          )}
        </div>
        <div className="detail-actions">
          {prices.data && (
            <DelayedBadge isDelayed={prices.data.is_delayed} asOf={prices.data.as_of} source={prices.data.source} />
          )}
          <button onClick={() => refresh.mutate()} disabled={refresh.isPending}>
            {refresh.isPending ? 'Fetching…' : 'Refresh prices'}
          </button>
        </div>
      </div>

      <Explainer title="New to this? How to read this chart">
        <dl>
          <dt>Candlesticks</dt>
          <dd>Each candle is one day. Green = price closed higher than it opened;
          red = closed lower. The thin "wick" shows the day's high and low; the thick
          "body" shows open→close.</dd>
          <dt>SMA20 / SMA50 (the blue &amp; orange lines)</dt>
          <dd><strong>Simple Moving Average</strong> — the average closing price over
          the last 20 (or 50) days. They smooth out noise to show the trend. When the
          faster line (20) is above the slower (50), the trend is generally up.</dd>
          <dt>Volume (bars at the bottom)</dt>
          <dd>How much was traded each day. Big moves backed by high volume are
          considered more meaningful.</dd>
          <dt>Period change / high / low</dt>
          <dd>Over the time range you've selected (1M = 1 month, 1Y = 1 year, etc.).</dd>
          <dt>Latest signal</dt>
          <dd>The app's current BUY / SELL / HOLD view for this coin. See the
          <strong> Signals</strong> page for the full reasoning.</dd>
        </dl>
      </Explainer>

      {stats && (
        <div className="stat-row">
          <div className="stat-tile"><div className="stat-label">Last close</div><div className="stat-value">{rands(stats.last)}</div></div>
          <div className="stat-tile">
            <div className="stat-label">Period change</div>
            <div className={`stat-value ${stats.changePct != null && stats.changePct >= 0 ? 'pnl-pos' : 'pnl-neg'}`}>
              {stats.changePct != null ? `${stats.changePct.toFixed(1)}%` : '—'}
            </div>
          </div>
          <div className="stat-tile"><div className="stat-label">Period high</div><div className="stat-value">{rands(stats.hi)}</div></div>
          <div className="stat-tile"><div className="stat-label">Period low</div><div className="stat-value">{rands(stats.lo)}</div></div>
          {latestSignal && (
            <div className="stat-tile">
              <div className="stat-label">Latest signal</div>
              <div className="stat-value" style={{ fontSize: '1.1rem' }}>
                <DirectionBadge direction={latestSignal.direction} />{' '}
                <Link to="/signals" className="muted" style={{ fontSize: '0.8rem' }}>details</Link>
              </div>
            </div>
          )}
        </div>
      )}

      <div className="range-bar">
        {RANGES.map((r) => (
          <button key={r.label} className={range === r.days ? 'range-btn range-btn--on' : 'range-btn'}
            onClick={() => setRange(r.days)}>{r.label}</button>
        ))}
      </div>

      {security.isError && <p className="error" role="alert">Unknown ticker "{ticker}".</p>}
      {(prices.isLoading || refresh.isPending) && <p>Loading prices…</p>}
      {prices.isError && <p className="error" role="alert">Could not load prices.</p>}
      {prices.data && allBars.length === 0 && !refresh.isPending && (
        <p className="muted">No price data available for {ticker} (the provider returned nothing).</p>
      )}

      {bars.length > 0 && <CandlestickChart bars={bars} />}

      <div className="detail-head" style={{ marginTop: '2rem' }}>
        <h2 className="section-title">Latest headlines</h2>
        <button onClick={() => refreshNews.mutate()} disabled={refreshNews.isPending}>
          {refreshNews.isPending ? 'Fetching…' : 'Refresh headlines'}
        </button>
      </div>
      <p className="muted" style={{ fontSize: '0.8rem' }}>
        Crypto news matched to this coin (from the configured news feed). Market
        sentiment for signals comes from the Fear &amp; Greed index, not from these.
      </p>
      {sens.isLoading && <p>Loading…</p>}
      {sens.data && sens.data.items.length === 0 && (
        <p className="muted">
          No headlines matched to {ticker} yet. Click “Refresh headlines”, or check the
          Dashboard for general crypto news.
        </p>
      )}
      {sens.data && sens.data.items.length > 0 && (
        <ul className="news-list">
          {sens.data.items.map((s) => (
            <li key={s.id} className="news-item">
              <div className="news-head">
                <a href={s.url} target="_blank" rel="noopener noreferrer">{s.headline}</a>
                {s.category && <span className="status">{s.category}</span>}
              </div>
              <div className="news-meta">
                {s.source}{s.published_at ? ` · ${new Date(s.published_at).toLocaleString()}` : ''}
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
