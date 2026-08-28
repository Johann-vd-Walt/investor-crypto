import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import { api, type BotEvent, type BotResponse } from '../api/client'
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
  const luno = useQuery({ queryKey: ['luno'], queryFn: api.getLunoStatus, refetchInterval: 30_000, retry: false })
  const [maxOrder, setMaxOrder] = useState('')
  const [dailyCap, setDailyCap] = useState('')

  const set = (d: BotResponse) => qc.setQueryData(['bot'], d)
  const start = useMutation({ mutationFn: api.startBot, onSuccess: set })
  const stop = useMutation({ mutationFn: api.stopBot, onSuccess: set })
  const reset = useMutation({ mutationFn: api.resetBot, onSuccess: set })
  const mode = useMutation({ mutationFn: (m: string) => api.setBotMode(m), onSuccess: set })
  const dryRun = useMutation({ mutationFn: (d: boolean) => api.setBotDryRun(d), onSuccess: set })
  const caps = useMutation({
    mutationFn: () => api.setBotCaps({
      max_order_usd: maxOrder ? Number(maxOrder) : undefined,
      daily_cap_usd: dailyCap ? Number(dailyCap) : undefined,
    }),
    onSuccess: (d) => { set(d); setMaxOrder(''); setDailyCap('') },
  })

  const s = q.data?.status
  const busy = start.isPending || stop.isPending || reset.isPending || mode.isPending || dryRun.isPending
  const isLive = s?.mode === 'live'
  const isReal = isLive && !s?.dry_run

  const modeLabel = !s ? '' : s.mode === 'paper' ? 'PAPER (simulated)' : (s.dry_run ? 'LIVE · DRY-RUN' : 'LIVE · REAL MONEY')
  const modeColor = !s ? '#334155' : s.mode === 'paper' ? '#334155' : (s.dry_run ? '#78350f' : '#7f1d1d')

  const goLive = () => {
    if (!confirm('Switch the bot to LIVE (Luno) mode?\n\nIt will start in DRY-RUN (no real orders) until you explicitly enable real trading.')) return
    mode.mutate('live')
  }
  const enableReal = () => {
    if (!confirm('⚠ ENABLE REAL TRADING\n\nThe bot will place REAL market orders on your Luno account with REAL money, capped per-order and per-day.\n\nThe strategy has NO proven edge and is expected to lose money. Continue?')) return
    if (!confirm('Are you absolutely sure? Real orders will begin on the next tick (~60s).')) return
    dryRun.mutate(false)
  }

  return (
    <section>
      <h1>Trading Bot <span style={{ fontSize: '0.6em', color: modeColor === '#7f1d1d' ? '#ef4444' : '#f59e0b' }}>· {modeLabel}</span></h1>

      <div className="banner" role="status" style={{ marginBottom: '1rem', background: modeColor, color: '#fff' }}>
        {q.data?.note}
      </div>

      <Explainer title="How the bot works & the safety ladder">
        <p>Every ~60s it pulls live prices, marks positions, exits on stop/horizon, and opens new
        positions from fresh BUY signals with realistic costs. It starts in <strong>paper</strong>
        (simulated). Live trading on Luno is gated so real orders can't happen by accident:</p>
        <ol>
          <li><strong>Paper</strong> — simulated, no exchange, no money (default).</li>
          <li><strong>Live · dry-run</strong> — connected to Luno, but logs the order it <em>would</em>
          send; places nothing.</li>
          <li><strong>Live · real</strong> — places real orders, only after you explicitly enable it,
          capped per-order and per-day, and only for the 11 coins Luno lists in USDT.</li>
        </ol>
        <p><strong>Honest expectation:</strong> the backtests show no established edge (Deflated Sharpe
        ~22%) and buy-and-hold won — so live trading is expected to <em>lose</em> money. Start tiny.</p>
      </Explainer>

      {/* Run controls */}
      <div className="filters" style={{ alignItems: 'center' }}>
        {s?.enabled ? (
          <button onClick={() => stop.mutate()} disabled={busy} style={{ background: '#7f1d1d' }}>⏸ Stop bot</button>
        ) : (
          <button onClick={() => start.mutate()} disabled={busy} style={{ background: '#14532d' }}>▶ Start bot</button>
        )}
        <button className="link" onClick={() => { if (confirm('Reset the PAPER portfolio? (Live positions are untouched.)')) reset.mutate() }} disabled={busy}>Reset paper</button>
        <span style={{ marginLeft: 'auto', color: s?.enabled ? '#22c55e' : '#94a3b8' }}>
          ● {s?.enabled ? 'Running' : 'Stopped'}
          {s?.last_tick_at && <span style={{ color: '#64748b' }}> · last tick {new Date(s.last_tick_at).toLocaleTimeString()}</span>}
        </span>
      </div>

      {/* Live trading (Luno) control panel */}
      <div style={{ border: `1px solid ${isReal ? '#7f1d1d' : '#334155'}`, borderRadius: 8, padding: '1rem', margin: '1rem 0' }}>
        <h2 style={{ marginTop: 0 }}>Live trading · Luno</h2>

        {!s?.luno_configured && (
          <p style={{ color: '#f59e0b' }}>
            No Luno API keys on the server. Add <code>LUNO_API_KEY_ID</code> and <code>LUNO_API_KEY_SECRET</code>
            to <code>backend/.env</code> and restart the service to enable live trading.
          </p>
        )}

        {/* Mode toggle */}
        <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', flexWrap: 'wrap' }}>
          <span style={{ color: '#94a3b8' }}>Mode:</span>
          <button onClick={() => mode.mutate('paper')} disabled={busy || s?.mode === 'paper'}
            style={{ background: s?.mode === 'paper' ? '#334155' : 'transparent' }}>Paper</button>
          <button onClick={goLive} disabled={busy || !s?.luno_configured || s?.mode === 'live'}
            title={!s?.luno_configured ? 'Add Luno keys first' : ''}
            style={{ background: isLive ? '#78350f' : 'transparent' }}>Live</button>

          {isLive && (
            s?.dry_run ? (
              <button onClick={enableReal} disabled={busy} style={{ background: '#7f1d1d', marginLeft: '1rem' }}>
                ⚠ Enable REAL trading
              </button>
            ) : (
              <button onClick={() => dryRun.mutate(true)} disabled={busy} style={{ background: '#14532d', marginLeft: '1rem' }}>
                ↩ Back to safe (dry-run)
              </button>
            )
          )}
          {isReal && (
            <button onClick={() => { if (confirm('KILL SWITCH: switch back to Paper and stop live trading?')) mode.mutate('paper') }}
              disabled={busy} style={{ background: '#450a0a', color: '#fff' }}>■ Kill switch → Paper</button>
          )}
        </div>

        {/* Caps */}
        {isLive && s && (
          <div style={{ marginTop: '1rem' }}>
            <div style={{ color: '#94a3b8', marginBottom: '0.25rem' }}>
              Guardrails — max <strong>{usd(s.max_order_usd)}</strong>/order, <strong>{usd(s.daily_cap_usd)}</strong>/day
              (spent today: {usd(s.daily_spent_usd)})
            </div>
            <div className="filters">
              <label>Max/order ${' '}
                <input type="number" value={maxOrder} onChange={(e) => setMaxOrder(e.target.value)} placeholder={String(s.max_order_usd)} style={{ width: '6rem' }} min="1" step="1" />
              </label>
              <label>Max/day ${' '}
                <input type="number" value={dailyCap} onChange={(e) => setDailyCap(e.target.value)} placeholder={String(s.daily_cap_usd)} style={{ width: '6rem' }} min="1" step="1" />
              </label>
              <button onClick={() => caps.mutate()} disabled={busy || (!maxOrder && !dailyCap)}>Save caps</button>
            </div>
          </div>
        )}

        {/* Luno balances */}
        {s?.luno_configured && (
          <div style={{ marginTop: '1rem' }}>
            <div style={{ color: '#94a3b8', marginBottom: '0.25rem' }}>Luno account (read-only)</div>
            {luno.data?.error && <p className="error">Luno: {luno.data.error}</p>}
            {luno.data?.balances.length ? (
              <table>
                <thead><tr><th>Asset</th><th>Available</th><th>Reserved</th><th>Total</th></tr></thead>
                <tbody>
                  {luno.data.balances.map((b) => (
                    <tr key={b.asset}>
                      <td><strong>{b.asset}</strong></td>
                      <td>{b.available.toLocaleString(undefined, { maximumFractionDigits: 8 })}</td>
                      <td>{b.reserved.toLocaleString(undefined, { maximumFractionDigits: 8 })}</td>
                      <td>{b.balance.toLocaleString(undefined, { maximumFractionDigits: 8 })}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : !luno.data?.error && <p className="muted">No non-zero balances (or fund your Luno USDT wallet to trade).</p>}
          </div>
        )}
        <p style={{ color: '#64748b', fontSize: '0.8rem', marginTop: '0.75rem' }}>
          Luno lists 11 of the app's coins in USDT (BTC→XBT, ETH, BNB, SOL, XRP, ADA, DOGE, LINK, TRX, XLM, BCH);
          signals for other coins are skipped in live mode. Luno has no test environment — your first real order
          is production. Start with a tiny max/order.
        </p>
      </div>

      {q.isError && <p className="error" role="alert">Could not load the bot.</p>}

      {/* Headline */}
      {s && (
        <div className="bt-metrics-row">
          <div className="bt-metrics">
            <h3>{isLive ? 'Equity (USDT + positions)' : 'Equity'}</h3>
            <div style={{ fontSize: '1.8rem', fontWeight: 700 }}>{usd(s.equity, 0)}</div>
            <div style={{ color: pnlColor(s.return_pct) }}>{signed(s.return_pct)}% vs start</div>
          </div>
          <div className="bt-metrics">
            <h3>Breakdown</h3>
            <table><tbody>
              <tr><td>{isLive ? 'USDT available' : 'Cash'}</td><td>{usd(s.cash, 0)}</td></tr>
              <tr><td>Realised P&amp;L</td><td style={{ color: pnlColor(s.realized_pnl) }}>{usd(s.realized_pnl)}</td></tr>
              <tr><td>Open positions</td><td>{s.open_positions}</td></tr>
            </tbody></table>
          </div>
        </div>
      )}

      {q.data && q.data.equity_curve.length > 1 && (
        <>
          <h2 className="section-title">Equity curve</h2>
          <div style={{ width: '100%', height: 240 }}>
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

      <h2 className="section-title">Open positions {isLive && <span className="muted">(live · Luno)</span>}</h2>
      {q.data && q.data.positions.length === 0 ? (
        <p className="muted">Flat — no open positions.</p>
      ) : (
        <table>
          <thead><tr><th>Coin</th><th>Qty</th><th>Entry</th><th>Live</th><th>Stop</th><th>Value</th><th>Unrealised</th></tr></thead>
          <tbody>
            {q.data?.positions.map((p) => (
              <tr key={p.ticker}>
                <td><strong>{p.ticker}</strong></td>
                <td>{p.quantity.toLocaleString(undefined, { maximumFractionDigits: 8 })}</td>
                <td>{usd(p.entry_price)}</td>
                <td>{usd(p.live_price)}</td>
                <td>{p.stop_price ? usd(p.stop_price) : '—'}</td>
                <td>{usd(p.market_value, 0)}</td>
                <td style={{ color: pnlColor(p.unrealized_pnl) }}>{usd(p.unrealized_pnl)} ({signed(p.unrealized_pct)}%)</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

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
    </section>
  )
}
