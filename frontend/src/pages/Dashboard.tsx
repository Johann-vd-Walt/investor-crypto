import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, type MacroSnapshotItem } from '../api/client'
import Explainer from '../components/Explainer'

function formatValue(item: MacroSnapshotItem): string {
  if (item.value === null) return '—'
  const v = item.value
  if (item.series_code === 'FNG') {
    // Fear & Greed index 0..100.
    const label = v >= 75 ? 'Extreme Greed' : v >= 55 ? 'Greed' : v >= 45 ? 'Neutral' : v >= 25 ? 'Fear' : 'Extreme Fear'
    return `${v.toFixed(0)} · ${label}`
  }
  // Crypto prices in USDT.
  return `$${v.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

function MacroCard({ item }: { item: MacroSnapshotItem }) {
  return (
    <div className={`macro-card ${item.available ? '' : 'macro-card--na'}`}>
      <div className="macro-label">{item.label}</div>
      {item.available ? (
        <>
          <div className="macro-value">{formatValue(item)}</div>
          <div className="macro-meta">
            {item.unit ? <span>{item.unit}</span> : null}
            <span className="macro-asof">
              as of {item.as_of ? new Date(item.as_of).toLocaleDateString() : '—'}
              {item.source ? ` · ${item.source}` : ''}
            </span>
          </div>
        </>
      ) : (
        <div className="macro-na" title={item.note ?? ''}>
          unavailable
          {item.note ? <div className="macro-note">{item.note}</div> : null}
        </div>
      )}
    </div>
  )
}

export default function Dashboard() {
  const qc = useQueryClient()
  const macro = useQuery({ queryKey: ['macro'], queryFn: api.getMacroSnapshot })

  const refresh = useMutation({
    mutationFn: () => api.runJob('ingest_macro'),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['macro'] }),
  })

  const news = useQuery({ queryKey: ['sens', 'recent'], queryFn: () => api.getSens(undefined, 15) })

  return (
    <section>
      <div className="detail-head">
        <h1>Dashboard</h1>
        <button onClick={() => refresh.mutate()} disabled={refresh.isPending}>
          {refresh.isPending ? 'Refreshing…' : 'Refresh macro'}
        </button>
      </div>

      <Explainer title="New to this? What the Dashboard shows">
        <p>This is your market overview. It tells you the mood of the crypto market
        right now — not what to buy.</p>
        <dl>
          <dt>Bitcoin (BTC / USDT)</dt>
          <dd>The price of 1 Bitcoin in <strong>USDT</strong> (a "stablecoin" pegged
          ≈ $1, used as the cash unit here). Crypto mostly moves <em>with</em> Bitcoin,
          so BTC is treated as "the market".</dd>
          <dt>Fear &amp; Greed</dt>
          <dd>A 0–100 mood gauge for crypto. Low = investors are fearful (prices often
          depressed); high = greedy (often over-heated). It's a widely-watched
          sentiment index, not a prediction.</dd>
          <dt>"as of" / stale banner</dt>
          <dd>When the data was last fetched. A yellow banner at the top means the
          background updater hasn't run recently — click a "Refresh" button.</dd>
        </dl>
      </Explainer>

      <h2 className="section-title">Market snapshot</h2>
      {macro.isLoading && <p>Loading…</p>}
      {macro.isError && (
        <p className="error" role="alert">Could not load the macro snapshot.</p>
      )}
      {macro.data && (
        <div className="macro-grid">
          {macro.data.items.map((item) => (
            <MacroCard key={item.series_code} item={item} />
          ))}
        </div>
      )}

      <h2 className="section-title">Latest crypto headlines</h2>
      {news.isLoading && <p>Loading…</p>}
      {news.data && news.data.items.length === 0 && (
        <p className="muted">No headlines yet — they load hourly from the crypto news feed.</p>
      )}
      {news.data && news.data.items.length > 0 && (
        <ul className="news-list">
          {news.data.items.map((s) => (
            <li key={s.id} className="news-item">
              <div className="news-head">
                <a href={s.url} target="_blank" rel="noopener noreferrer">{s.headline}</a>
                {s.ticker && <span className="status">{s.ticker}</span>}
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
