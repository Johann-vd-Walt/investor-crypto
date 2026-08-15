import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import { api, type BotEvent } from '../api/client'
import Explainer from '../components/Explainer'

function usd(n: number | null | undefined, dp = 2) {
  if (n === null || n === undefined) return '—'
  return `$${n.toLocaleString(undefined, { minimumFractionDigits: dp, maximumFractionDigits: dp })}`
}
function signed(n: number | null | undefined) {
  if (n === null || n === undefined) return '—'
  return `${n >= 0 ? '+' : ''}${n.toLocaleString(undefined, { maximumFractionDigits: 2 })}`
}

const KIND_COLOR: Record<string, string> = {
  open: '#22c55e', close: '#f59e0b', start: '#58a6ff', stop: '#94a3b8',
  error: '#ef4444', info: '#64748b', skip: '#64748b',
}

function pnlColor(n: number | null | undefined) {
  if (n === null || n === undefined) return '#e6edf3'
  return n >= 0 ? '#22c55e' : '#ef4444'
}

export default function Bot() {
  const qc = useQueryClient()
  const q = useQuery({ queryKey: ['bot'], queryFn: api.getBot, refetchInterval: 10_000 })

  const start = useMutation({ mutationFn: api.startBot, onSuccess: (d) => qc.setQueryData(['bot'], d) })
  const stop = useMutation({ mutationFn: api.stopBot, onSuccess: (d) => qc.setQueryData(['bot'], d) })
  const reset = useMutation({
    mutationFn: api.resetBot,
    onSuccess: (d) => qc.setQueryData(['bot'], d),
  })

  const s = q.data?.status
  const busy = start.isPending || stop.isPending || reset.isPending

  return (
    <section>
      <h1>Trading Bot <span style={{ fontSize: '0.6em', color: '#f59e0b' }}>· PAPER (simulated)</span></h1>

      <div className="banner banner-warn" role="status" style={{ marginBottom: '1rem' }}>
        💡 This bot places <strong>no real orders</strong> — it simulates fills against live prices with
        no exchange keys and no real money. The backtests show <strong>no established edge</strong>
        (Deflated Sharpe ~22%) and buy-and-hold beat the strategy, so expect it to lose to simply
        holding BTC. Watch it here before ever considering real money.
      </div>

      <Explainer title="What is this bot doing?">
        <p>Every ~60 seconds it pulls <strong>live prices</strong>, marks your simulated positions to
        market, exits any that hit their stop or time limit, and opens new simulated positions for
        fresh BUY signals the strategy produced — all with realistic fees and slippage. It starts with
        ${(s?.initial_cash ?? 100000).toLocaleString()} of pretend cash.</p>
        <p>Notice that a new position usually shows a small <em>loss</em> the instant it opens — that's
        the cost of trading (fees + slippage), and it's exactly why frequent trading is hard to win at.
        <strong> Green equity curve = doing well on paper; but paper ≠ proven.</strong></p>
      </Explainer>

      {/* Controls + headline */}
      <div className="filters" style={{ alignItems: 'center' }}>
        {s?.enabled ? (
          <button onClick={() => stop.mutate()} disabled={busy} style={{ background: '#7f1d1d' }}>
            ⏸ Stop bot
          </button>
        ) : (
          <button onClick={() => start.mutate()} disabled={busy} style={{ background: '#14532d' }}>
            ▶ Start bot
          </button>
        )}
        <button className="link" onClick={() => { if (confirm('Reset the paper portfolio to starting cash? This clears all simulated positions and history.')) reset.mutate() }} disabled={busy}>
          Reset portfolio
        </button>
        <span style={{ marginLeft: 'auto', color: s?.enabled ? '#22c55e' : '#94a3b8' }}>
          ● {s?.enabled ? 'Running' : 'Stopped'}
          {s?.last_tick_at && <span style={{ color: '#64748b' }}> · last tick {new Date(s.last_tick_at).toLocaleTimeString()}</span>}
        </span>
      </div>

      {q.isError && <p className="error" role="alert">Could not load the bot.</p>}

      {s && (
        <div className="bt-metrics-row" style={{ marginTop: '1rem' }}>
          <div className="bt-metrics">
            <h3>Equity</h3>
            <div style={{ fontSize: '1.8rem', fontWeight: 700 }}>{usd(s.equity, 0)}</div>
            <div style={{ color: pnlColor(s.return_pct) }}>{signed(s.return_pct)}% vs start</div>
          </div>
          <div className="bt-metrics">
            <h3>Breakdown</h3>
            <table><tbody>
              <tr><td>Cash</td><td>{usd(s.cash, 0)}</td></tr>
              <tr><td>Realised P&amp;L</td><td style={{ color: pnlColor(s.realized_pnl) }}>{usd(s.realized_pnl)}</td></tr>
              <tr><td>Open positions</td><td>{s.open_positions}</td></tr>
              <tr><td>Started</td><td>{s.started_at ? new Date(s.started_at).toLocaleDateString() : '—'}</td></tr>
            </tbody></table>
          </div>
        </div>
      )}

      {q.data && q.data.equity_curve.length > 1 && (
        <>
          <h2 className="section-title">Equity curve (live)</h2>
          <div style={{ width: '100%', height: 260 }}>
            <ResponsiveContainer>
              <LineChart data={q.data.equity_curve.map((p) => ({ t: new Date(p.ts).toLocaleTimeString(), equity: p.equity }))}>
                <CartesianGrid stroke="#21262d" />
                <XAxis dataKey="t" tick={{ fontSize: 10, fill: '#8b949e' }} stroke="#30363d" minTickGap={40} />
                <YAxis domain={['auto', 'auto']} tick={{ fontSize: 11, fill: '#8b949e' }} width={70} stroke="#30363d" />
                <Tooltip contentStyle={{ background: '#161b22', border: '1px solid #30363d' }} />
                <Line type="monotone" dataKey="equity" stroke="#58a6ff" dot={false} strokeWidth={2} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </>
      )}

      {/* Open positions */}
      <h2 className="section-title">Open positions</h2>
      {q.data && q.data.positions.length === 0 ? (
        <p className="muted">Flat — no open positions. The strategy isn't always in the market; the bot
        opens one when a fresh BUY signal appears.</p>
      ) : (
        <table>
          <thead>
            <tr><th>Coin</th><th>Qty</th><th>Entry</th><th>Live</th><th>Stop</th><th>Value</th><th>Unrealised</th></tr>
          </thead>
          <tbody>
            {q.data?.positions.map((p) => (
              <tr key={p.ticker}>
                <td><strong>{p.ticker}</strong></td>
                <td>{p.quantity}</td>
                <td>{usd(p.entry_price)}</td>
                <td>{usd(p.live_price)}</td>
                <td>{p.stop_price ? usd(p.stop_price) : '—'}</td>
                <td>{usd(p.market_value, 0)}</td>
                <td style={{ color: pnlColor(p.unrealized_pnl) }}>
                  {usd(p.unrealized_pnl)} ({signed(p.unrealized_pct)}%)
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {/* Activity log */}
      <h2 className="section-title">Activity log</h2>
      {q.data && q.data.events.length === 0 ? (
        <p className="muted">No activity yet.</p>
      ) : (
        <div style={{ maxHeight: 320, overflowY: 'auto', border: '1px solid #21262d', borderRadius: 6 }}>
          <table>
            <tbody>
              {q.data?.events.map((e: BotEvent, i) => (
                <tr key={i}>
                  <td style={{ color: '#64748b', whiteSpace: 'nowrap', fontSize: '0.8rem' }}>{new Date(e.created_at).toLocaleString()}</td>
                  <td style={{ color: KIND_COLOR[e.kind] ?? '#e6edf3', textTransform: 'uppercase', fontSize: '0.72rem' }}>{e.kind}</td>
                  <td>{e.ticker ?? ''}</td>
                  <td style={{ color: '#cbd5e1' }}>{e.detail}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <p style={{ color: '#64748b', fontSize: '0.85rem', marginTop: '1rem' }}>
        {q.data?.note}
      </p>
    </section>
  )
}
