import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { api, type PositioningTone } from '../api/client'
import Explainer from '../components/Explainer'

const TONE_STYLE: Record<PositioningTone, { bg: string; label: string }> = {
  bull: { bg: '#14532d', label: 'bullish' },
  bear: { bg: '#7f1d1d', label: 'bearish' },
  warn: { bg: '#78350f', label: 'caution' },
  neutral: { bg: '#334155', label: 'neutral' },
}

function ToneTag({ tone }: { tone: PositioningTone }) {
  const t = TONE_STYLE[tone]
  return (
    <span style={{ background: t.bg, color: '#fff', borderRadius: 4, padding: '1px 8px', fontSize: '0.75rem', textTransform: 'uppercase', letterSpacing: '0.03em' }}>
      {t.label}
    </span>
  )
}

export default function Positioning() {
  const q = useQuery({
    queryKey: ['positioning'],
    queryFn: api.getPositioning,
    refetchInterval: 10 * 60 * 1000,
  })

  return (
    <section>
      <h1>Positioning · Derivatives</h1>

      <Explainer title="What is this and how do I use it?">
        <p>This reads the <strong>free Binance futures market</strong> to show how leveraged
        traders are positioned — the one category of extra data with genuine, evidence-backed
        value. It is <strong>context, not a buy/sell trigger</strong>, and the app still never
        trades for you.</p>
        <ul>
          <li><strong>Funding</strong> — what perpetual-swap traders pay to hold a position.
          Extreme positive = crowded longs (flush risk); extreme negative = crowded shorts
          (squeeze fuel). Flagged only at the top/bottom of each coin's own recent range.</li>
          <li><strong>Open interest</strong> — how much leveraged money is committed. Combined
          with price it tells you whether a move is <em>new money</em> (durable) or just
          <em> short-covering</em> (weaker).</li>
          <li><strong>Taker flow</strong> — whether aggressive market orders are mostly buying
          or selling (short-horizon).</li>
          <li><strong>Top traders</strong> — the largest accounts' long/short lean. Lowest
          confidence — treat as colour only.</li>
        </ul>
        <p>Everything is a <strong>percentile of the coin's own history</strong>, so the flags
        adapt as regimes drift. History builds up over time as the collector runs a few times
        a day.</p>
      </Explainer>

      {q.isLoading && <p>Loading…</p>}
      {q.isError && <p className="error" role="alert">Could not load positioning. Is the backend running?</p>}

      {q.data && q.data.count === 0 && (
        <p>No futures positioning data yet. The collector runs a few times a day (02:25 / 10:25 /
        18:25 SAST) — check back once it has run, or trigger <code>ingest_derivatives</code>. If it
        stays empty, the server may not be able to reach Binance's futures host.</p>
      )}

      {q.data?.items.map((snap) => (
        <div key={snap.ticker} style={{ border: '1px solid #334155', borderRadius: 8, padding: '1rem', marginBottom: '1rem' }}>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: '0.75rem', marginBottom: '0.5rem' }}>
            <h2 style={{ margin: 0 }}>
              <Link to={`/security/${snap.ticker}`}>{snap.ticker}</Link>
            </h2>
            <span style={{ color: '#94a3b8' }}>{snap.name}</span>
            {snap.as_of && <span style={{ color: '#64748b', fontSize: '0.8rem', marginLeft: 'auto' }}>as of {new Date(snap.as_of).toLocaleString()}</span>}
          </div>

          {!snap.available && <p style={{ color: '#94a3b8' }}>{snap.note}</p>}

          {snap.available && (
            <table>
              <thead>
                <tr><th>Signal</th><th></th><th>Read</th><th>Sample</th></tr>
              </thead>
              <tbody>
                {snap.signals.map((s) => (
                  <tr key={s.metric}>
                    <td><strong>{s.label}</strong></td>
                    <td><ToneTag tone={s.tone} /></td>
                    <td style={{ color: '#cbd5e1' }}>{s.detail}</td>
                    <td style={{ color: '#64748b' }}>{s.sample}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      ))}

      {q.data && q.data.count > 0 && (
        <p style={{ color: '#64748b', fontSize: '0.85rem' }}>
          Context only — none of these is a standalone signal, and they are strongest at
          extremes. The evidence is that funding and open-interest divergence carry real
          (if modest) information; the top-trader lean is the weakest and easily over-read.
        </p>
      )}
    </section>
  )
}
