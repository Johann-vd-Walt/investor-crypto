import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import {
  CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import { api, type BacktestMetrics, type MomentumMetrics } from '../api/client'
import Explainer from '../components/Explainer'

function pct(n: number | null | undefined) {
  return n === null || n === undefined ? '—' : `${(n * 100).toFixed(0)}%`
}
function num(n: number | null | undefined, dp = 2) {
  return n === null || n === undefined ? '—' : n.toFixed(dp)
}
function rands(n: number | null | undefined) {
  return n === null || n === undefined ? '—' : `$${n.toLocaleString(undefined, { maximumFractionDigits: 0 })}`
}

function MetricsTable({ title, m, highlight }: { title: string; m: BacktestMetrics | null; highlight?: boolean }) {
  return (
    <div className={`bt-metrics ${highlight ? 'bt-metrics--hl' : ''}`}>
      <h3>{title}</h3>
      {!m || m.trades === 0 ? (
        <p className="muted">No trades.</p>
      ) : (
        <table>
          <tbody>
            <tr><td>Trades</td><td>{m.trades}</td></tr>
            <tr><td>Win rate</td><td>{pct(m.win_rate)} ({m.wins}/{m.trades})</td></tr>
            <tr><td>Avg return / trade</td><td>{num(m.avg_return_pct)}%</td></tr>
            <tr><td>Expectancy / trade</td><td>{rands(m.expectancy)}</td></tr>
            <tr><td>Profit factor</td><td>{num(m.profit_factor)}</td></tr>
            <tr><td>Reward / risk</td><td>{num(m.reward_risk)}</td></tr>
            <tr><td>Total P&amp;L (net)</td><td>{rands(m.total_pnl)}</td></tr>
            <tr><td>Avg hold</td><td>{num(m.avg_hold_days, 1)} days</td></tr>
            <tr><td>Max drawdown</td><td>{rands(m.max_drawdown)} ({num(m.max_drawdown_pct, 1)}%)</td></tr>
            <tr><td>Sharpe (per trade)</td><td>{num(m.sharpe)}</td></tr>
            <tr>
              <td>Prob. Sharpe &gt; 0</td>
              <td style={{ color: (m.psr ?? 0) >= 0.95 ? '#22c55e' : '#f59e0b' }}>{pct(m.psr)}</td>
            </tr>
            <tr>
              <td>Deflated Sharpe ({m.trials} trial{m.trials === 1 ? '' : 's'})</td>
              <td style={{ color: (m.deflated_sharpe ?? 0) >= 0.95 ? '#22c55e' : '#f59e0b', fontWeight: 600 }}>{pct(m.deflated_sharpe)}</td>
            </tr>
          </tbody>
        </table>
      )}
    </div>
  )
}

function EquityChart({ data, dataKey }: { data: object[]; dataKey: string }) {
  return (
    <div style={{ width: '100%', height: 300 }}>
      <ResponsiveContainer>
        <LineChart data={data} margin={{ top: 10, right: 20, bottom: 0, left: 0 }}>
          <CartesianGrid stroke="#21262d" />
          <XAxis dataKey="date" tick={{ fontSize: 11, fill: '#8b949e' }} stroke="#30363d" />
          <YAxis tick={{ fontSize: 11, fill: '#8b949e' }} width={70} stroke="#30363d" />
          <Tooltip contentStyle={{ background: '#161b22', border: '1px solid #30363d', color: '#e6edf3' }} />
          <Line type="monotone" dataKey={dataKey} stroke="#58a6ff" dot={false} strokeWidth={2} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}

export default function Backtest() {
  const [strategy, setStrategy] = useState<'technical' | 'momentum'>('momentum')
  const [tickers, setTickers] = useState('')
  const [splitDate, setSplitDate] = useState('')
  const [topK, setTopK] = useState('10')
  const [rebalance, setRebalance] = useState('21')
  const [trials, setTrials] = useState('1')

  const tech = useMutation({
    mutationFn: () =>
      api.runBacktest({
        tickers: tickers.trim() ? tickers.split(',').map((t) => t.trim().toUpperCase()) : undefined,
        split_date: splitDate || undefined,
        trials: Math.max(1, Number(trials) || 1),
      }),
  })
  const mom = useMutation({
    mutationFn: () =>
      api.runMomentumBacktest({
        tickers: tickers.trim() ? tickers.split(',').map((t) => t.trim().toUpperCase()) : undefined,
        top_k: Number(topK),
        rebalance_days: Number(rebalance),
        split_date: splitDate || undefined,
        trials: Math.max(1, Number(trials) || 1),
      }),
  })

  const momCols = (label: string, mm: MomentumMetrics, highlight = false) => (
    <div className={`bt-metrics ${highlight ? 'bt-metrics--hl' : ''}`}>
      <h3>{label}</h3>
      <table><tbody>
        <tr><td>Rebalances</td><td>{mm.n_rebalances}</td></tr>
        <tr><td>Total return</td><td>{num(mm.total_return_pct, 1)}%</td></tr>
        <tr><td>Annualised</td><td>{num(mm.annualised_return_pct, 1)}%</td></tr>
        <tr><td>Sharpe</td><td>{num(mm.sharpe)}</td></tr>
        <tr><td>Max drawdown</td><td>{num(mm.max_drawdown_pct, 1)}%</td></tr>
        <tr><td>Winning periods</td><td>{pct(mm.win_rate_periods)}</td></tr>
        <tr>
          <td>Prob. Sharpe &gt; 0</td>
          <td style={{ color: (mm.psr ?? 0) >= 0.95 ? '#22c55e' : '#f59e0b' }}>{pct(mm.psr)}</td>
        </tr>
        <tr>
          <td>Deflated Sharpe ({mm.trials} trial{mm.trials === 1 ? '' : 's'})</td>
          <td style={{ color: (mm.deflated_sharpe ?? 0) >= 0.95 ? '#22c55e' : '#f59e0b', fontWeight: 600 }}>{pct(mm.deflated_sharpe)}</td>
        </tr>
      </tbody></table>
    </div>
  )

  const t = tech.data
  const m = mom.data
  const pending = tech.isPending || mom.isPending

  return (
    <section>
      <h1>Backtest</h1>

      <Explainer title="New to this? What a backtest tells you">
        <p>A <strong>backtest</strong> replays a strategy over past data to see how it
        <em>would</em> have done — a reality check before risking money. Past results
        don't guarantee future ones.</p>
        <dl>
          <dt>Strategy: Technical vs Momentum</dt>
          <dd><strong>Technical</strong> = trade each coin on its own chart signals.
          <strong> Momentum</strong> = each period, hold the handful of coins that have
          risen the most lately (a classic "ride the winners" approach).</dd>
          <dt>Out-of-sample (OOS)</dt>
          <dd>Results split by date. The <strong>OOS</strong> column is the honest one —
          it's on data the settings weren't chosen on. Beware anything that looks great
          on the full sample but poor OOS (that's <strong>overfitting</strong> — a
          strategy tuned to fit the past by luck).</dd>
          <dt>Key numbers</dt>
          <dd><strong>Total / annualised return</strong> = profit %. <strong>Sharpe</strong>
          = return earned per unit of "bumpiness" (higher is better; &gt;1 is decent).
          <strong> Max drawdown</strong> = the worst peak-to-trough drop — how much pain
          you'd have endured (a −80% drawdown means you'd have lost 80% at the low).
          <strong> Profit factor</strong> = gross wins ÷ gross losses (&gt;1 = profitable).</dd>
          <dt>Benchmark</dt>
          <dd>Compares the strategy to simply <strong>buying and holding</strong> (incl.
          Bitcoin). If holding beats the strategy, the strategy isn't adding value — a
          crucial, humbling check.</dd>
          <dt>Prob. Sharpe &amp; Deflated Sharpe</dt>
          <dd><strong>Prob. Sharpe &gt; 0</strong> is the probability the edge is real
          given the sample size and the shape of returns. <strong>Deflated Sharpe</strong>
          goes further and penalises it for how many settings you've tried (enter that in
          "Configs tried") — because if you test enough configurations, one will look good
          by luck. Below <strong>95%</strong>, treat the edge as <em>not established</em>.
          Note: a high score means the per-trade edge is statistically non-zero — it does
          <strong> not</strong> mean the strategy beats buy-and-hold. Always read it next
          to the benchmark.</dd>
        </dl>
      </Explainer>

      <div className="filters">
        <label>Strategy{' '}
          <select value={strategy} onChange={(e) => setStrategy(e.target.value as 'technical' | 'momentum')}>
            <option value="momentum">Cross-sectional momentum</option>
            <option value="technical">Technical signal</option>
          </select>
        </label>
        <label>Tickers{' '}
          <input placeholder="blank = all with prices" value={tickers}
            onChange={(e) => setTickers(e.target.value)} style={{ width: '14rem' }} />
        </label>
        <label>OOS from{' '}
          <input type="date" value={splitDate} onChange={(e) => setSplitDate(e.target.value)} />
        </label>
        {strategy === 'momentum' && (
          <>
            <label>Top K{' '}
              <input type="number" value={topK} onChange={(e) => setTopK(e.target.value)} style={{ width: '4rem' }} min="1" />
            </label>
            <label>Rebalance (days){' '}
              <input type="number" value={rebalance} onChange={(e) => setRebalance(e.target.value)} style={{ width: '4rem' }} min="5" />
            </label>
          </>
        )}
        <label title="How many settings have you tried? The Deflated Sharpe penalises the result for this many attempts.">Configs tried{' '}
          <input type="number" value={trials} onChange={(e) => setTrials(e.target.value)} style={{ width: '4rem' }} min="1" />
        </label>
        <button onClick={() => (strategy === 'momentum' ? mom.mutate() : tech.mutate())} disabled={pending}>
          {pending ? 'Running…' : 'Run backtest'}
        </button>
      </div>

      <div className="banner banner-info">
        {strategy === 'momentum'
          ? 'Equal-weight long-only: hold the top-K liquid coins by trailing momentum, rebalanced periodically. Net of exchange fees, no lookahead. Compare to buy-and-hold / Bitcoin.'
          : 'Technical-signal walk-forward, net of costs, no lookahead. Macro & sentiment excluded. Read the out-of-sample column.'}
      </div>

      {(tech.isError || mom.isError) && <p className="error" role="alert">Backtest failed.</p>}

      {/* --- Momentum result --- */}
      {strategy === 'momentum' && m && (
        <>
          <p className="muted">{m.tickers_tested} securities · top {m.top_k} every {m.rebalance_days}d{m.split_date ? ` · OOS split ${m.split_date}` : ''}</p>
          <div className="bt-metrics-row">
            {momCols('Full sample', m.full)}
            {m.out_of_sample && momCols('Out-of-sample (headline)', m.out_of_sample, true)}
            <div className="bt-metrics">
              <h3>Benchmark (full window)</h3>
              <table><tbody>
                <tr><td>Buy &amp; hold (avg)</td><td>{num(m.benchmark.buy_hold_avg_pct, 1)}%</td></tr>
                <tr><td>Bitcoin (BTC)</td><td>{num(m.benchmark.btc_pct, 1)}%</td></tr>
                <tr><td>Window</td><td>{m.benchmark.window_start} → {m.benchmark.window_end}</td></tr>
              </tbody></table>
            </div>
          </div>

          {m.latest_holdings.length > 0 && (
            <p><strong>Momentum says hold now:</strong>{' '}
              {m.latest_holdings.map((h) => <span key={h} className="status" style={{ marginRight: '0.3rem' }}>{h}</span>)}
            </p>
          )}

          {m.equity_curve.length > 0 && (
            <>
              <h2 className="section-title">Equity curve (growth of R1, net)</h2>
              <EquityChart data={m.equity_curve} dataKey="equity" />
            </>
          )}
          <p className="disclaimer-inline">{m.scope_note} {m.disclaimer}</p>
        </>
      )}

      {/* --- Technical result --- */}
      {strategy === 'technical' && t && (
        <>
          <p className="muted">{t.tickers_tested} securities tested{t.split_date ? ` · OOS split ${t.split_date}` : ''}</p>
          <div className="bt-metrics-row">
            <MetricsTable title="Full sample" m={t.full} />
            {t.out_of_sample && <MetricsTable title="Out-of-sample (headline)" m={t.out_of_sample} highlight />}
          </div>
          <div className="bt-metrics" style={{ maxWidth: 540 }}>
            <h3>Benchmark — did the signal beat just holding?</h3>
            <table><tbody>
              <tr><td>Window</td><td>{t.benchmark.window_start ?? '—'} → {t.benchmark.window_end ?? '—'}</td></tr>
              <tr><td>Buy &amp; hold (avg of tested assets)</td><td>{num(t.benchmark.buy_hold_avg_pct)}%</td></tr>
              <tr><td>Bitcoin (same window)</td><td>{num(t.benchmark.btc_pct)}%</td></tr>
              <tr><td>Strategy avg return / trade</td><td>{num(t.full.avg_return_pct)}%</td></tr>
            </tbody></table>
          </div>
          {t.equity_curve.length > 0 && (
            <>
              <h2 className="section-title">Equity curve ({t.split_date ? 'out-of-sample' : 'full'}, net P&amp;L)</h2>
              <EquityChart data={t.equity_curve} dataKey="cumulative_pnl" />
            </>
          )}
          <p className="disclaimer-inline">{t.scope_note} {t.disclaimer}</p>
        </>
      )}
    </section>
  )
}
