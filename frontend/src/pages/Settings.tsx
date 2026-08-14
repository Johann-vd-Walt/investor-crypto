import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, type AppSettings } from '../api/client'
import Explainer from '../components/Explainer'

const FIELDS: { key: keyof AppSettings; label: string; step: string }[] = [
  { key: 'weight_technical', label: 'Weight: technical', step: '0.05' },
  { key: 'weight_macro', label: 'Weight: macro', step: '0.05' },
  { key: 'weight_sentiment', label: 'Weight: sentiment', step: '0.05' },
  { key: 'weight_momentum', label: 'Weight: momentum', step: '0.05' },
  { key: 'buy_threshold', label: 'Buy threshold', step: '0.05' },
  { key: 'sell_threshold', label: 'Sell threshold', step: '0.05' },
  { key: 'default_horizon_days', label: 'Horizon (days)', step: '1' },
  { key: 'account_size', label: 'Account size (R)', step: '1000' },
  { key: 'risk_per_trade_pct', label: 'Risk per trade (%)', step: '0.25' },
  { key: 'atr_stop_multiple', label: 'ATR stop multiple', step: '0.25' },
  { key: 'trailing_stop_pct', label: 'Trailing stop (%, 0=off)', step: '0.5' },
  { key: 'brokerage_pct', label: 'Brokerage (%/side)', step: '0.05' },
  { key: 'slippage_pct', label: 'Slippage (%/side)', step: '0.05' },
  { key: 'stt_pct', label: 'STT (%, buys)', step: '0.05' },
  { key: 'min_liquidity_zar', label: 'Min liquidity (R/day)', step: '500000' },
  { key: 'liquidity_lookback_days', label: 'Liquidity lookback (days)', step: '1' },
  { key: 'momentum_lookback_days', label: 'Momentum lookback (days)', step: '5' },
  { key: 'momentum_skip_days', label: 'Momentum skip (days)', step: '1' },
  { key: 'max_open_positions', label: 'Max open positions', step: '1' },
  { key: 'max_positions_per_sector', label: 'Max per sector', step: '1' },
]

export default function Settings() {
  const qc = useQueryClient()
  const settings = useQuery({ queryKey: ['settings'], queryFn: api.getSettings })
  const [form, setForm] = useState<Record<string, string>>({})
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    if (settings.data) {
      const f: Record<string, string> = {}
      for (const { key } of FIELDS) f[key] = String(settings.data[key])
      setForm(f)
    }
  }, [settings.data])

  const save = useMutation({
    mutationFn: () => {
      const overrides: Record<string, number> = {}
      for (const { key } of FIELDS) overrides[key] = Number(form[key])
      return api.updateSettings(overrides)
    },
    onSuccess: () => {
      setSaved(true)
      qc.invalidateQueries({ queryKey: ['settings'] })
      setTimeout(() => setSaved(false), 2500)
    },
  })

  const wsum =
    (Number(form.weight_technical) || 0) +
    (Number(form.weight_macro) || 0) +
    (Number(form.weight_sentiment) || 0) +
    (Number(form.weight_momentum) || 0)
  const weightsOk = Math.abs(wsum - 1) <= 0.001

  return (
    <section>
      <h1>Settings</h1>
      <p className="muted">
        Overrides persist in the database and take effect on the next signal/backtest
        run (no restart). Blank the database row to fall back to <code>.env</code> defaults.
      </p>

      <Explainer title="New to this? What these settings mean">
        <p>These control how the engine scores and sizes trades. The defaults are
        reasonable — change one at a time and re-check the Backtest.</p>
        <dl>
          <dt>Weights (technical / macro / sentiment / momentum)</dt>
          <dd>How much each ingredient counts toward the final score. They should add up
          to about 1.00. Set momentum to 0 to switch it off.</dd>
          <dt>Buy / sell threshold</dt>
          <dd>How strong the score must be to trigger a BUY (default +0.3) or SELL
          (−0.3). Higher buy threshold = fewer, more selective signals.</dd>
          <dt>Horizon (days)</dt>
          <dd>How long a trade is held before it's closed if nothing else triggers.</dd>
          <dt>Account size &amp; risk per trade</dt>
          <dd>Your pretend capital (USDT) and the % of it you're willing to lose on one
          trade. These size the positions. 1% risk is conservative/typical.</dd>
          <dt>ATR stop multiple / trailing stop</dt>
          <dd><strong>ATR</strong> = Average True Range (daily volatility). The stop-loss
          is placed this many ATRs below entry. A <strong>trailing stop</strong> (%) rises
          as the price rises to lock in gains (0 = off).</dd>
          <dt>Brokerage / slippage / STT (%)</dt>
          <dd>Cost assumptions used in simulations. Brokerage = exchange fee per side;
          slippage = getting a slightly worse price than expected; STT = a JSE share tax,
          not applicable to crypto (leave 0). Honest costs stop backtests flattering you.</dd>
          <dt>Min liquidity / momentum lookback / max positions</dt>
          <dd>Filters &amp; limits: skip coins that trade too little to enter safely; how
          far back momentum looks; and caps on how many positions (total and per category)
          can be open at once.</dd>
        </dl>
      </Explainer>

      {settings.isLoading && <p>Loading…</p>}

      {settings.data && (
        <>
          <div className="settings-grid">
            {FIELDS.map(({ key, label, step }) => (
              <label key={key} className="settings-field">
                <span>{label}</span>
                <input
                  type="number" step={step} value={form[key] ?? ''}
                  onChange={(e) => setForm((f) => ({ ...f, [key]: e.target.value }))}
                />
              </label>
            ))}
          </div>

          <p className={weightsOk ? 'muted' : 'error'}>
            Weights sum = {wsum.toFixed(2)} {weightsOk ? '✓' : '— should be 1.00 (fusion normalises, but keep it clean)'}
          </p>

          <button onClick={() => save.mutate()} disabled={save.isPending}>
            {save.isPending ? 'Saving…' : 'Save settings'}
          </button>
          {saved && <span className="pnl-pos" style={{ marginLeft: '0.75rem' }}>Saved ✓</span>}

          <h2 className="section-title">Data providers</h2>
          <ul className="provider-list">
            {Object.entries(settings.data.providers).map(([k, on]) => (
              <li key={k}>
                <span className={on ? 'dot-on' : 'dot-off'} /> {k}: {on ? 'active' : 'not configured'}
              </li>
            ))}
          </ul>
          <p className="muted">Data freshness is shown by the banner at the top of every page (from /api/health).</p>
        </>
      )}
    </section>
  )
}
