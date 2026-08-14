import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { api, type Signal, type SignalDirection, type SignalStatus } from '../api/client'
import DirectionBadge from '../components/DirectionBadge'
import RationaleView from '../components/RationaleView'
import Explainer from '../components/Explainer'

function fmt(n: number | null, dp = 2, prefix = '') {
  return n === null || n === undefined ? '—' : `${prefix}${n.toFixed(dp)}`
}

function SignalCard({ sig }: { sig: Signal }) {
  const qc = useQueryClient()
  const [open, setOpen] = useState(false)
  const status = useMutation({
    mutationFn: (s: SignalStatus) => api.setSignalStatus(sig.id, s),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['signals'] }),
  })

  return (
    <div className="signal-card">
      <div className="signal-head">
        <div className="signal-title">
          <Link to={`/security/${sig.ticker}`}><strong>{sig.ticker}</strong></Link>
          <DirectionBadge direction={sig.direction} />
          <span className={`status status--${sig.status.toLowerCase()}`}>{sig.status}</span>
        </div>
        <div className="signal-score">score {fmt(sig.score, 3)}</div>
      </div>

      <div className="signal-metrics">
        <span>tech {fmt(sig.technical_score, 2)}</span>
        <span>macro {fmt(sig.macro_score, 2)}</span>
        <span>sentiment {fmt(sig.sentiment_score, 2)}</span>
        <span title="From the engine's measured historical hit rate">
          confidence {sig.confidence === null ? 'n/a (no track record yet)' : fmt(sig.confidence, 2)}
        </span>
      </div>

      {sig.direction !== 'HOLD' && (
        <div className="signal-trade">
          entry {fmt(sig.suggested_entry, 2, '$')} · stop {fmt(sig.suggested_stop, 2, '$')} · size {sig.suggested_size ?? '—'}
          <span className="muted"> (horizon {sig.horizon_days}d)</span>
        </div>
      )}

      <div className="signal-actions">
        <button className="secondary" onClick={() => setOpen((o) => !o)}>
          {open ? 'Hide rationale' : 'Why?'}
        </button>
        <button onClick={() => status.mutate('ACTED')} disabled={status.isPending}>Mark acted</button>
        <button className="link" onClick={() => status.mutate('DISMISSED')} disabled={status.isPending}>
          Dismiss
        </button>
      </div>

      {open && <RationaleView rationale={sig.rationale} />}
    </div>
  )
}

export default function Signals() {
  const qc = useQueryClient()
  const [direction, setDirection] = useState<SignalDirection | ''>('')
  const [minScore, setMinScore] = useState<string>('')

  const signals = useQuery({
    queryKey: ['signals', direction, minScore],
    queryFn: () =>
      api.listSignals({
        direction: direction || undefined,
        minScore: minScore === '' ? undefined : Number(minScore),
      }),
  })

  const generate = useMutation({
    mutationFn: () => api.runJob('generate_signals'),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['signals'] }),
  })

  return (
    <section>
      <div className="detail-head">
        <h1>Signals</h1>
        <button onClick={() => generate.mutate()} disabled={generate.isPending}>
          {generate.isPending ? 'Generating…' : 'Generate signals'}
        </button>
      </div>

      <Explainer title="New to this? Understanding a signal">
        <p>A "signal" is the app's suggested view on a coin — <strong>not advice, and
        frequently wrong</strong>. Each one is an <em>explainable</em> score, not a
        black box.</p>
        <dl>
          <dt>BUY / SELL / HOLD</dt>
          <dd>The direction. It comes from a combined <strong>score</strong> between
          −1 (very bearish) and +1 (very bullish). Above +0.3 → BUY; below −0.3 → SELL;
          in between → HOLD (do nothing).</dd>
          <dt>The score is a blend of four "layers"</dt>
          <dd><strong>Technical</strong> = chart patterns (moving averages, RSI, MACD,
          breakouts). <strong>Macro</strong> = overall market regime (is Bitcoin
          trending up or down?). <strong>Sentiment</strong> = the Fear &amp; Greed mood.
          <strong>Momentum</strong> = is this coin strong vs the others? Click
          <strong> "Why?"</strong> on any signal to see exactly which fired.</dd>
          <dt>Acronyms</dt>
          <dd><strong>RSI</strong> (Relative Strength Index): 0–100; under 30 = "oversold"
          (maybe cheap), over 70 = "overbought" (maybe pricey).
          <strong> MACD</strong>: a momentum indicator; positive = upward push.
          <strong> ATR</strong> (Average True Range): how much the price typically moves
          in a day — used to place the stop.</dd>
          <dt>entry / stop / size</dt>
          <dd>If it's a BUY: a suggested buy price, a <strong>stop-loss</strong> (a price
          to sell at to cap your loss), and how many units the risk rule suggests. These
          are illustrative — the app does not execute them.</dd>
          <dt>confidence</dt>
          <dd>Blank until the app has a real track record of closed paper trades. It
          never shows a made-up number.</dd>
          <dt>Mark acted / Dismiss</dt>
          <dd>Just for your own record-keeping — whether you acted on or ignored a signal.</dd>
        </dl>
      </Explainer>

      <div className="filters">
        <label>
          Direction{' '}
          <select value={direction} onChange={(e) => setDirection(e.target.value as SignalDirection | '')}>
            <option value="">All</option>
            <option value="BUY">Buy</option>
            <option value="SELL">Sell</option>
            <option value="HOLD">Hold</option>
          </select>
        </label>
        <label>
          Min score{' '}
          <input
            type="number" step="0.1" min="-1" max="1" style={{ width: '5rem' }}
            value={minScore} onChange={(e) => setMinScore(e.target.value)}
          />
        </label>
      </div>

      {signals.isLoading && <p>Loading…</p>}
      {signals.isError && <p className="error" role="alert">Could not load signals.</p>}
      {signals.data && signals.data.items.length === 0 && (
        <p className="muted">
          No signals yet. Click “Generate signals” (needs ≥50 daily bars per security).
        </p>
      )}

      {signals.data?.items.map((sig) => <SignalCard key={sig.id} sig={sig} />)}

      <p className="disclaimer-inline">
        Signals are probabilistic estimates and can be wrong — not advice. Confidence
        reflects the engine's own measured hit rate (blank until it has a track record).
      </p>
    </section>
  )
}
