import { useEffect, useState, type ReactNode } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { api, type AppSettings, type AuditFinding } from '../api/client'

const SEV: Record<AuditFinding['severity'], { bg: string; label: string }> = {
  critical: { bg: '#7f1d1d', label: 'CRITICAL' },
  warn: { bg: '#78350f', label: 'WARNING' },
  good: { bg: '#14532d', label: 'OK' },
  info: { bg: '#334155', label: 'INFO' },
}
const pct = (n: number | null | undefined) => (n == null ? '—' : `${n.toFixed(0)}%`)

type FieldKey = keyof AppSettings

interface FieldMeta {
  label: string
  step?: string
  kind?: 'number' | 'bool' | 'select' | 'text'
  options?: { value: string; label: string }[]
}

const META: Partial<Record<FieldKey, FieldMeta>> = {
  weight_technical: { label: 'Weight · technical', step: '0.05' },
  weight_macro: { label: 'Weight · macro/regime', step: '0.05' },
  weight_sentiment: { label: 'Weight · sentiment', step: '0.05' },
  weight_momentum: { label: 'Weight · momentum', step: '0.05' },
  weight_flow: { label: 'Weight · flow (real-time)', step: '0.05' },
  flow_momentum_days: { label: 'Flow lookback (days)', step: '1' },
  buy_threshold: { label: 'Buy threshold', step: '0.05' },
  sell_threshold: { label: 'Sell threshold', step: '0.05' },
  default_horizon_days: { label: 'Hold horizon (days)', step: '1' },
  momentum_lookback_days: { label: 'Momentum lookback (days)', step: '5' },
  momentum_skip_days: { label: 'Momentum skip (days)', step: '1' },
  account_size: { label: 'Account size (USDT)', step: '1000' },
  risk_per_trade_pct: { label: 'Risk per trade (%)', step: '0.25' },
  atr_stop_multiple: { label: 'ATR stop multiple', step: '0.25' },
  trailing_stop_pct: { label: 'Trailing stop (%, 0=off)', step: '0.5' },
  max_open_positions: { label: 'Max open positions', step: '1' },
  max_positions_per_sector: { label: 'Max per category', step: '1' },
  brokerage_pct: { label: 'Brokerage (%/side)', step: '0.05' },
  slippage_pct: { label: 'Slippage (%/side)', step: '0.05' },
  stt_pct: { label: 'STT (%, 0 for crypto)', step: '0.05' },
  min_liquidity_zar: { label: 'Min liquidity (USDT/day)', step: '500000' },
  liquidity_lookback_days: { label: 'Liquidity lookback (days)', step: '1' },
  regime_mode: {
    label: 'Regime mode', kind: 'select',
    options: [
      { value: 'classic', label: 'Classic (BTC 20-day move only)' },
      { value: 'two_speed', label: 'Two-speed (long-term trend + 20-day move)' },
    ],
  },
  regime_long_sma_days: { label: 'Long-term trend SMA (days)', step: '10' },
  sentiment_mode: {
    label: 'Fear & Greed mode', kind: 'select',
    options: [
      { value: 'trend', label: 'Trend (greed +, fear −)' },
      { value: 'contrarian', label: 'Contrarian (extreme fear +, extreme greed −)' },
    ],
  },
  contrarian_band: { label: 'Contrarian band (F&G ≤ band / ≥ 100−band)', step: '5' },
  pullback_entry: { label: 'Pullback entry', kind: 'bool' },
  pullback_rsi: { label: 'Pullback RSI below', step: '1' },
  dip_horizon_days: { label: 'Dip-entry hold (days, 0 = normal)', step: '1' },
  dip_atr_stop_multiple: { label: 'Dip-entry ATR stop multiple', step: '0.25' },
  luno_only_universe: { label: 'Only coins tradeable on Luno', kind: 'bool' },
  bot_trade_signals: { label: 'Bot opens trades from signals', kind: 'bool' },
  dca_enabled: { label: 'Accumulation on', kind: 'bool' },
  dca_ticker: { label: 'Coin (e.g. BTCUSDT)', kind: 'text' },
  dca_amount_usd: { label: 'Amount per buy (USDT)', step: '5' },
  dca_interval_days: { label: 'Every (days)', step: '1' },
  dca_min_drawdown_pct: { label: 'Only when ≥ % below 1-year high (0 = always)', step: '5' },
}

const ALL_FIELDS = Object.keys(META) as FieldKey[]

interface Section {
  id: string
  title: string
  tag?: string
  body: ReactNode
  fields: FieldKey[]
}

const SECTIONS: Section[] = [
  {
    id: 'fusion',
    title: '1 · The decision engine (signal fusion)',
    tag: 'core',
    body: (
      <>
        <p>Every day the engine forms <strong>four independent opinions</strong> about each coin,
        each a number from −1 (bearish) to +1 (bullish), and blends them with the weights below into
        one <strong>fused score</strong>. If that score clears the <strong>buy threshold</strong>, it
        produces a BUY with an entry, a stop-loss and a size. That signal is what the paper bot and
        paper-trading act on.</p>
        <p><strong>Tuning:</strong> weights should add to about 1.00 (set any layer to 0 to switch it
        off). A higher buy threshold means fewer, more selective trades. This is the highest-leverage
        knob — small changes reshape everything downstream.</p>
      </>
    ),
    fields: ['weight_technical', 'weight_macro', 'weight_sentiment', 'weight_momentum', 'weight_flow', 'buy_threshold', 'sell_threshold', 'default_horizon_days'],
  },
  {
    id: 'technical',
    title: '2 · Technical layer',
    body: (
      <>
        <p>Reads each coin's <strong>own chart</strong>: trend via moving-average relationships
        (SMA/EMA), momentum via <strong>RSI</strong> (overbought/oversold) and <strong>MACD</strong>
        (trend strength/turns), and price <strong>breakouts</strong>. It's positive when the chart
        looks like an uptrend is starting. This is the only layer backtested on its own (the
        Technical backtest), so it's the most measurable — and, honestly, it lost to buy-and-hold.</p>
        <p>Its influence is set by <em>Weight · technical</em> above; the indicator periods themselves
        are fixed in code (sensible defaults).</p>
      </>
    ),
    fields: [],
  },
  {
    id: 'macro',
    title: '3 · Macro / regime layer',
    body: (
      <>
      <p>One market-wide read taken from <strong>Bitcoin's trend</strong>. Because the whole market
      tends to follow BTC, this layer <strong>damps buys when BTC is in a downtrend</strong> and
      supports them when it's rising — the app's "don't fight the tide." Same value applied to every
      coin. Influence set by <em>Weight · macro/regime</em>.</p>
      <p><strong>Classic</strong> looks only at BTC's 20-day move, so it flips to "risk-off" on a
      ±3% edge, even in the middle of a bull market. <strong>Two-speed</strong> first asks whether
      BTC is above its long-term average (the trend), then uses the 20-day move for the phase. A
      pullback while BTC is still above its long-term trend counts as a <strong>dip-buy window</strong>
      (mildly positive) instead of risk-off. Below the long-term trend it stays defensive.</p>
      </>
    ),
    fields: ['regime_mode', 'regime_long_sma_days'],
  },
  {
    id: 'sentiment',
    title: '4 · Sentiment layer',
    body: (
      <>
      <p>The <strong>Fear &amp; Greed index</strong> (0–100), mapped to −1..+1 and applied
      market-wide. It's a weak, slow signal, so keep its weight modest. Influence set by
      <em> Weight · sentiment</em>. See it live on the <Link to="/context">Context</Link> page.</p>
      <p><strong>Trend</strong> mode (original) scores fear as negative, so the deeper a sell-off goes the
      less the bot wants to buy. <strong>Contrarian</strong> mode scores only the extremes: fear at or
      below the band is buy-side, greed at or above 100 − band is sell-side, and the middle is neutral.
      The evidence for contrarian F&amp;G is weaker than for the trend tools.</p>
      </>
    ),
    fields: ['sentiment_mode', 'contrarian_band'],
  },
  {
    id: 'momentum',
    title: '5 · Momentum (ride the winners)',
    body: (
      <>
        <p>A <strong>cross-sectional</strong> strategy: rank all liquid coins by their recent return
        and favour the leaders. It looks back <em>momentum lookback</em> days but <strong>skips</strong>
        the most recent few days (short-term moves often reverse). Momentum is the best-documented
        crypto anomaly — but it's <strong>cost-fragile</strong> and strongest in smaller, harder-to-trade
        coins, so real-world edge is thin. It's also its own strategy on the
        <Link to="/backtest"> Backtest</Link> page.</p>
      </>
    ),
    fields: ['momentum_lookback_days', 'momentum_skip_days'],
  },
  {
    id: 'flow',
    title: '5b · Real-time flow',
    tag: 'unbacktestable',
    body: (
      <>
        <p>A short-horizon read of <strong>who's buying right now</strong>: recent price momentum (a
        few days) plus <strong>taker buy/sell pressure</strong> from the derivatives feed (see
        <Link to="/positioning"> Positioning</Link> and the Market-movers panel). Positive when a coin
        is moving up on aggressive buying.</p>
        <p><strong>Read this honestly:</strong> unlike the other layers, flow <strong>cannot be
        backtested</strong> — there's no point-in-time history of pressure data — so you're trusting
        it on faith. And "chasing the movers" frequently buys the top right before it reverses. Keep
        the weight <strong>modest</strong> (default 0.10). Set it to 0 to ignore real-time flow
        entirely; raise it if you want the bot to lean into what's being bought <em>now</em>.</p>
      </>
    ),
    fields: ['flow_momentum_days'],
  },
  {
    id: 'dip',
    title: '5c · Dip buying',
    tag: 'opt-in',
    body: (
      <>
        <p>The original technical layer only rewards RSI below 30, which rarely happens in a pullback
        inside an uptrend. With <strong>pullback entry</strong> on, while a coin is above its long-term
        average (same SMA length as the regime), an RSI below the pullback level and a retest of the
        50-day average both count as buy-side. Such a trade is a <strong>dip entry</strong>: it holds
        longer and uses a wider stop. The risk rule then makes the position smaller, so the dollar
        risk stays the same.</p>
        <p><strong>Only coins tradeable on Luno</strong> limits signals and backtests to the coins the
        live bot can actually buy, so what you test is what you trade.</p>
        <p>Test before you trust: run the <Link to="/backtest">Technical backtest</Link> with
        <em> + BTC regime &amp; Fear/Greed</em> ticked, before and after.</p>
      </>
    ),
    fields: ['pullback_entry', 'pullback_rsi', 'dip_horizon_days', 'dip_atr_stop_multiple', 'luno_only_universe'],
  },
  {
    id: 'dca',
    title: '5d · Accumulation (recurring buy)',
    tag: 'opt-in',
    body: (
      <>
        <p>This doesn't try to time the market. The <Link to="/bot">bot</Link> buys a fixed amount of
        one coin every N days, but <strong>only while the price is at least the set % below its 1-year
        high</strong> (0 = always). These holdings are <strong>never auto-sold</strong>. They show as
        ACCUM on the Bot page and are kept separate from signal trades.</p>
        <p>The same safety rails apply: paper by default, the dry-run switch, and the per-order and
        daily caps on the Bot page. The amount per buy is clipped to those caps. It only runs while
        the bot is started.</p>
        <p>Untick <strong>Bot opens trades from signals</strong> to run accumulation on its own: the bot
        stops opening new signal trades but still manages and exits any it already holds.</p>
      </>
    ),
    fields: ['bot_trade_signals', 'dca_enabled', 'dca_ticker', 'dca_amount_usd', 'dca_interval_days', 'dca_min_drawdown_pct'],
  },
  {
    id: 'risk',
    title: '6 · Risk & position sizing',
    tag: 'important',
    body: (
      <>
        <p>This decides <strong>how much</strong> to buy and <strong>where to bail</strong> — and it
        matters more than entry signals. Position size is set so that if the stop is hit you lose
        about <strong>risk per trade %</strong> of your account. The stop sits
        <strong> ATR-stop-multiple × ATR</strong> (a volatility measure) below entry, so more volatile
        coins get wider stops and smaller positions. A <strong>trailing stop</strong> (%) ratchets up
        as price rises to lock gains (0 = off). Caps limit how many positions run at once.</p>
        <p><strong>Tuning:</strong> 1% risk is conservative/typical; 2%+ is aggressive. Wider ATR stops
        = fewer stop-outs but bigger losses when they hit.</p>
      </>
    ),
    fields: ['account_size', 'risk_per_trade_pct', 'atr_stop_multiple', 'trailing_stop_pct', 'max_open_positions', 'max_positions_per_sector'],
  },
  {
    id: 'costs',
    title: '7 · Trading costs',
    body: (
      <p>Every simulation subtracts <strong>brokerage + slippage</strong> on each side. Slippage =
      getting a slightly worse price than you hoped. STT is a JSE <em>share</em> tax — leave it 0 for
      crypto. <strong>Honest costs are what stop a backtest from flattering you</strong>; don't lower
      these to make results look better — that's lying to yourself. This is exactly why the paper bot
      shows a small loss the instant a position opens.</p>
    ),
    fields: ['brokerage_pct', 'slippage_pct', 'stt_pct'],
  },
  {
    id: 'liquidity',
    title: '8 · Liquidity filter',
    body: (
      <p>Skips coins that trade too little to enter or exit safely — the minimum average daily traded
      value over a lookback window. This prevents fake "edge" that only exists in coins you couldn't
      actually trade at size.</p>
    ),
    fields: ['min_liquidity_zar', 'liquidity_lookback_days'],
  },
]

export default function Strategy() {
  const qc = useQueryClient()
  const settings = useQuery({ queryKey: ['settings'], queryFn: api.getSettings })
  const [form, setForm] = useState<Record<string, string>>({})
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    if (settings.data) {
      const f: Record<string, string> = {}
      for (const k of ALL_FIELDS) f[k] = String(settings.data[k])
      setForm(f)
    }
  }, [settings.data])

  const audit = useMutation({ mutationFn: api.auditStrategy })

  const save = useMutation({
    mutationFn: () => {
      const overrides: Record<string, number | string | boolean> = {}
      for (const k of ALL_FIELDS) {
        const kind = META[k]!.kind ?? 'number'
        overrides[k] = kind === 'number' ? Number(form[k]) : kind === 'bool' ? form[k] === 'true' : form[k]
      }
      return api.updateSettings(overrides)
    },
    onSuccess: () => {
      setSaved(true)
      qc.invalidateQueries({ queryKey: ['settings'] })
      qc.invalidateQueries({ queryKey: ['strategy-settings'] })
      setTimeout(() => setSaved(false), 2500)
    },
  })

  const wsum = ['weight_technical', 'weight_macro', 'weight_sentiment', 'weight_momentum', 'weight_flow']
    .reduce((a, k) => a + (Number(form[k]) || 0), 0)
  const weightsOk = Math.abs(wsum - 1) <= 0.001

  const field = (k: FieldKey) => {
    const m = META[k]!
    const set = (v: string) => setForm((f) => ({ ...f, [k]: v }))
    const kind = m.kind ?? 'number'
    return (
      <label key={k} className="settings-field">
        <span>{m.label}</span>
        {kind === 'bool' ? (
          <input type="checkbox" checked={form[k] === 'true'}
            onChange={(e) => set(e.target.checked ? 'true' : 'false')} />
        ) : kind === 'select' ? (
          <select value={form[k] ?? ''} onChange={(e) => set(e.target.value)}>
            {m.options!.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
        ) : (
          <input type={kind === 'text' ? 'text' : 'number'} step={m.step} value={form[k] ?? ''}
            onChange={(e) => set(e.target.value)} />
        )}
      </label>
    )
  }

  return (
    <section>
      <h1>Strategy</h1>

      <div className="banner banner-warn" role="status" style={{ marginBottom: '1rem' }}>
        These are the strategies the app runs and the knobs that tune them. One honest rule:
        <strong> tuning against past data is how you fool yourself</strong>. After any change, re-run the
        <Link to="/backtest"> Backtest</Link> and read the <strong>Deflated Sharpe</strong> — if it's
        below ~95%, the "improvement" is probably luck, not edge.
      </div>

      <p className="muted">
        The pipeline: five layers → a fused score (−1…+1) → if it clears the buy threshold, a BUY with
        an entry, stop and size → the <Link to="/bot">paper bot</Link> / paper-trading acts on it.
        Nothing here is proven to beat simply holding BTC.
      </p>

      {/* Strategy auditor */}
      <div style={{ border: '1px solid #334155', borderRadius: 8, padding: '1rem', marginBottom: '1.25rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', flexWrap: 'wrap' }}>
          <button onClick={() => audit.mutate()} disabled={audit.isPending}>
            {audit.isPending ? 'Reviewing… (runs a backtest)' : '🔍 Review my strategy'}
          </button>
          <span className="muted">Audits your current settings + a fresh backtest + the bot's track record, and tells you honestly what to fix.</span>
        </div>
        {audit.isError && <p className="error" style={{ marginTop: '0.75rem' }}>Audit failed.</p>}
        {audit.data && (
          <div style={{ marginTop: '1rem' }}>
            {audit.data.metrics && (
              <div className="muted" style={{ fontSize: '0.85rem', marginBottom: '0.5rem' }}>
                Momentum backtest: return <strong>{pct(audit.data.metrics.total_return_pct)}</strong> vs
                hold BTC <strong>{pct(audit.data.metrics.btc_buyhold_pct)}</strong> · Deflated Sharpe{' '}
                <strong style={{ color: (audit.data.metrics.deflated_sharpe ?? 0) >= 0.95 ? '#22c55e' : '#f59e0b' }}>
                  {pct((audit.data.metrics.deflated_sharpe ?? 0) * 100)}
                </strong> · {audit.data.metrics.rebalances} rebalances
              </div>
            )}
            {audit.data.findings.map((f, i) => (
              <div key={i} style={{ borderLeft: `4px solid ${SEV[f.severity].bg}`, background: '#161b22', borderRadius: 4, padding: '0.6rem 0.85rem', marginBottom: '0.5rem' }}>
                <div style={{ display: 'flex', gap: '0.6rem', alignItems: 'baseline' }}>
                  <span style={{ background: SEV[f.severity].bg, color: '#fff', borderRadius: 3, padding: '1px 7px', fontSize: '0.68rem' }}>{SEV[f.severity].label}</span>
                  <strong>{f.title}</strong>
                </div>
                <div style={{ color: '#cbd5e1', fontSize: '0.9rem', marginTop: '0.25rem' }}>{f.detail}</div>
                {f.suggestion && <div style={{ color: '#58a6ff', fontSize: '0.85rem', marginTop: '0.2rem' }}>→ {f.suggestion}</div>}
              </div>
            ))}
          </div>
        )}
      </div>

      {settings.isLoading && <p>Loading…</p>}

      {settings.data && (
        <>
          {SECTIONS.map((s) => (
            <div key={s.id} style={{ border: '1px solid #334155', borderRadius: 8, padding: '1rem 1.25rem', marginBottom: '1.25rem' }}>
              <h2 style={{ marginTop: 0 }}>
                {s.title}
                {s.tag && <span style={{ marginLeft: '0.6rem', fontSize: '0.6em', textTransform: 'uppercase', color: '#f59e0b', letterSpacing: '0.05em' }}>{s.tag}</span>}
              </h2>
              <div style={{ color: '#cbd5e1', fontSize: '0.92rem' }}>{s.body}</div>
              {s.fields.length > 0 && (
                <div className="settings-grid" style={{ marginTop: '0.75rem' }}>
                  {s.fields.map(field)}
                </div>
              )}
              {s.id === 'fusion' && (
                <p className={weightsOk ? 'muted' : 'error'} style={{ marginBottom: 0 }}>
                  Weights sum = {wsum.toFixed(2)} {weightsOk ? '✓' : '— aim for 1.00'}
                </p>
              )}
            </div>
          ))}

          <div style={{ position: 'sticky', bottom: 0, background: '#0d1117', padding: '0.75rem 0', borderTop: '1px solid #21262d', display: 'flex', alignItems: 'center', gap: '1rem' }}>
            <button onClick={() => save.mutate()} disabled={save.isPending}>
              {save.isPending ? 'Saving…' : 'Save strategy changes'}
            </button>
            {saved && <span className="pnl-pos">Saved ✓ — now re-run the Backtest to sanity-check</span>}
            {save.isError && <span className="error">Save failed.</span>}
            <span className="muted" style={{ marginLeft: 'auto' }}>
              Applies on the next signal/backtest run — no restart. Same store as <Link to="/settings">Settings</Link>.
            </span>
          </div>
        </>
      )}
    </section>
  )
}
