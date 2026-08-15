import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { api, type CoinConsensus } from '../api/client'
import Explainer from '../components/Explainer'

function LeanBar({ c }: { c: CoinConsensus }) {
  const total = c.traders || 1
  const longPct = (c.longs / total) * 100
  return (
    <div style={{ display: 'flex', height: 14, width: 140, borderRadius: 4, overflow: 'hidden', background: '#7f1d1d' }}>
      <div style={{ width: `${longPct}%`, background: '#14532d' }} title={`${c.longs} long`} />
    </div>
  )
}

export default function Consensus() {
  const q = useQuery({
    queryKey: ['consensus'],
    queryFn: api.getConsensus,
    refetchInterval: 15 * 60 * 1000,
    retry: false,
  })

  const inUniverse = q.data?.items.filter((i) => i.ticker) ?? []
  const other = q.data?.items.filter((i) => !i.ticker) ?? []

  return (
    <section>
      <h1>Crowd Consensus <span style={{ fontSize: '0.7em', color: '#f59e0b' }}>· experimental</span></h1>

      <div className="banner banner-warn" role="status" style={{ marginBottom: '1rem' }}>
        ⚠ Weakest signal in the app. This is <strong>context, not advice, and never a signal to
        copy</strong>. Leaderboards are riddled with survivorship bias, latency, and manipulation —
        most “top traders” are indistinguishable from lucky ones. The app never trades for you.
      </div>

      <Explainer title="What is this, honestly?">
        <p>It reads OKX’s public copy-trading leaderboard and tallies how many of the top lead
        traders are currently <strong>net long vs net short</strong> each coin. The idea is a
        crowd/consensus view — harder to fake than any single “guru”.</p>
        <p><strong>Why to be sceptical:</strong> by the time a position is visible the move has
        usually happened; the board only ever shows this month’s survivors; and positions can be
        part of a hedge you can’t see. Treat a strong lean as a mild talking point, not a reason
        to act. Prefer the <Link to="/positioning">Positioning</Link> page — its funding/OI signals
        have real evidence behind them; this one does not.</p>
      </Explainer>

      {q.isLoading && <p>Loading… (first load fetches live from OKX and can take a few seconds)</p>}
      {q.isError && <p className="error" role="alert">Could not reach OKX’s public API right now.</p>}

      {q.data && !q.data.available && <p>No consensus data available right now.</p>}

      {q.data?.available && (
        <>
          <p style={{ color: '#64748b', fontSize: '0.85rem' }}>
            Sampled {q.data.traders_sampled} top lead traders · cache age {Math.round(q.data.as_of_cache_age_s / 60)} min
          </p>

          {inUniverse.length > 0 && (
            <>
              <h2>Coins you track</h2>
              <ConsensusTable rows={inUniverse} linked />
            </>
          )}

          {other.length > 0 && (
            <>
              <h2 style={{ marginTop: '1.5rem' }}>Other coins the traders hold</h2>
              <ConsensusTable rows={other} />
            </>
          )}
        </>
      )}
    </section>
  )
}

function ConsensusTable({ rows, linked = false }: { rows: CoinConsensus[]; linked?: boolean }) {
  return (
    <table>
      <thead>
        <tr><th>Coin</th><th>Long/short</th><th></th><th>Lean</th><th>Traders</th></tr>
      </thead>
      <tbody>
        {rows.map((c) => (
          <tr key={c.inst}>
            <td>
              {linked && c.ticker
                ? <Link to={`/security/${c.ticker}`}><strong>{c.ticker}</strong></Link>
                : <span>{c.inst.replace('-SWAP', '')}</span>}
            </td>
            <td style={{ color: '#94a3b8' }}>{c.longs}L / {c.shorts}S</td>
            <td><LeanBar c={c} /></td>
            <td style={{ textTransform: 'uppercase', fontSize: '0.75rem', color: c.lean === 'long' ? '#22c55e' : c.lean === 'short' ? '#ef4444' : '#94a3b8' }}>{c.lean}</td>
            <td style={{ color: '#64748b' }}>{c.traders}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}
