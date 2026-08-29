import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import { api, type PaperPerformance } from '../api/client'
import Explainer from '../components/Explainer'
import { fmtDate } from '../format'

function StatTile({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="stat-tile">
      <div className="stat-label">{label}</div>
      <div className="stat-value">{value}</div>
      {hint && <div className="stat-hint">{hint}</div>}
    </div>
  )
}

function rands(n: number | null | undefined) {
  if (n === null || n === undefined) return '—'
  return `$${n.toLocaleString(undefined, { maximumFractionDigits: 2 })}`
}

function EdgeBanner({ perf }: { perf: PaperPerformance }) {
  if (perf.has_edge_data) return null
  return (
    <div className="banner banner-warn" role="status">
      Measured edge not yet meaningful: {perf.sample_size} of {perf.min_sample} closed
      paper trades needed before a win rate is reported. Confidence stays blank until then —
      no invented numbers.
    </div>
  )
}

export default function PaperPerformance() {
  const qc = useQueryClient()
  const perf = useQuery({ queryKey: ['paper-perf'], queryFn: api.getPaperPerformance })
  const trades = useQuery({ queryKey: ['paper-trades'], queryFn: api.getPaperTrades })

  const update = useMutation({
    mutationFn: () => api.runJob('update_paper_trades'),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['paper-perf'] })
      qc.invalidateQueries({ queryKey: ['paper-trades'] })
    },
  })

  const p = perf.data

  return (
    <section>
      <div className="detail-head">
        <h1>Paper performance</h1>
        <button onClick={() => update.mutate()} disabled={update.isPending}>
          {update.isPending ? 'Updating…' : 'Update paper trades'}
        </button>
      </div>

      <Explainer title="New to this? What is paper trading?">
        <p><strong>Paper trading</strong> = pretend/simulated trading with fake money.
        When the engine issues a BUY, it opens a make-believe position and tracks what
        <em>would</em> have happened — so you can judge the strategy <strong>before</strong>
        risking real money. No real funds are involved.</p>
        <dl>
          <dt>Win rate</dt>
          <dd>The % of closed simulated trades that made a profit. Only shown once there
          are enough of them to mean anything.</dd>
          <dt>Avg return / trade &amp; Total P&amp;L</dt>
          <dd><strong>P&amp;L</strong> = profit and loss, in USDT, <strong>after</strong>
          subtracting estimated exchange fees. Negative = losing money.</dd>
          <dt>Equity curve</dt>
          <dd>A line of your simulated running profit over time. Up and to the right is
          good; deep dips are drawdowns.</dd>
          <dt>Open vs closed</dt>
          <dd>Open = a simulated position still running; closed = it hit its stop-loss or
          time limit and was booked.</dd>
        </dl>
      </Explainer>

      {perf.isLoading && <p>Loading…</p>}
      {perf.isError && <p className="error" role="alert">Could not load performance.</p>}

      {p && (
        <>
          <EdgeBanner perf={p} />

          <div className="stat-row">
            <StatTile
              label="Win rate"
              value={p.win_rate === null ? 'n/a' : `${(p.win_rate * 100).toFixed(0)}%`}
              hint={p.win_rate === null ? 'not enough trades' : `${p.wins}/${p.sample_size} wins`}
            />
            <StatTile
              label="Avg return / trade"
              value={p.avg_return_pct === null ? 'n/a' : `${p.avg_return_pct.toFixed(2)}%`}
              hint="net of costs"
            />
            <StatTile label="Total P&L" value={rands(p.total_pnl)} hint="net of brokerage + slippage" />
            <StatTile label="Closed trades" value={String(p.sample_size)} />
          </div>

          <h2 className="section-title">Equity curve (net P&amp;L, cumulative)</h2>
          {p.equity_curve.length === 0 ? (
            <p className="muted">No closed paper trades yet.</p>
          ) : (
            <div style={{ width: '100%', height: 300 }}>
              <ResponsiveContainer>
                <LineChart data={p.equity_curve} margin={{ top: 10, right: 20, bottom: 0, left: 0 }}>
                  <CartesianGrid stroke="#21262d" />
                  <XAxis dataKey="date" tick={{ fontSize: 11, fill: '#8b949e' }} stroke="#30363d" />
                  <YAxis tick={{ fontSize: 11, fill: '#8b949e' }} width={70} stroke="#30363d" />
                  <Tooltip formatter={(v) => rands(Number(v))} contentStyle={{ background: '#161b22', border: '1px solid #30363d', color: '#e6edf3' }} />
                  <Line type="monotone" dataKey="cumulative_pnl" stroke="#58a6ff" dot={false} strokeWidth={2} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}
        </>
      )}

      <h2 className="section-title">Paper trades</h2>
      {trades.data && (
        <p className="muted">
          Open positions: <strong>{trades.data.filter((t) => t.status === 'OPEN').length}</strong>
          {' '}· closed: {trades.data.filter((t) => t.status === 'CLOSED').length}
          {' '}(portfolio caps enforced when signals open trades — see Settings)
        </p>
      )}
      {trades.data && trades.data.length === 0 && (
        <p className="muted">
          No paper trades yet. They open automatically from BUY signals (Signals → Generate).
        </p>
      )}
      {trades.data && trades.data.length > 0 && (
        <table>
          <thead>
            <tr>
              <th>Ticker</th><th>Status</th><th>Entry</th><th>Qty</th>
              <th>Exit</th><th>P&amp;L (net)</th><th>Unrealized</th>
            </tr>
          </thead>
          <tbody>
            {trades.data.map((t) => (
              <tr key={t.id}>
                <td><strong>{t.ticker}</strong></td>
                <td>{t.status}</td>
                <td>{rands(t.entry_price)}<br /><span className="muted">{fmtDate(t.entry_datetime)}</span></td>
                <td>{t.quantity.toLocaleString(undefined, { maximumFractionDigits: 8 })}</td>
                <td>{t.exit_price ? rands(t.exit_price) : '—'}</td>
                <td className={t.pnl != null ? (t.pnl >= 0 ? 'pnl-pos' : 'pnl-neg') : ''}>{rands(t.pnl)}</td>
                <td className={t.unrealized_pnl != null ? (t.unrealized_pnl >= 0 ? 'pnl-pos' : 'pnl-neg') : ''}>{rands(t.unrealized_pnl)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  )
}
