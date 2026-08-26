import { useState, type FormEvent } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, ApiError, type TaxSummary, type TradeSide } from '../api/client'
import Explainer from '../components/Explainer'

function rands(n: number | null | undefined) {
  if (n === null || n === undefined) return '—'
  const abs = Math.abs(n)
  const dp = abs >= 1 ? 2 : abs >= 0.01 ? 4 : 8
  return `$${n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: dp })}`
}

function downloadTaxCsv(summary: TaxSummary) {
  const header = ['symbol', 'sell_datetime', 'quantity', 'proceeds_usdt', 'base_cost_usdt', 'gain_usdt', 'unmatched_qty']
  const rows = summary.disposals.map((d) => [
    d.ticker, d.sell_datetime, d.quantity, d.proceeds, d.base_cost, d.gain, d.unmatched_quantity,
  ])
  rows.push([])
  rows.push(['TOTAL', '', '', summary.total_proceeds, summary.total_base_cost, summary.total_realised_gain, ''])
  const csv = [header, ...rows].map((r) => r.join(',')).join('\n')
  const blob = new Blob([csv], { type: 'text/csv' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `tax-summary-${summary.tax_year}.csv`
  a.click()
  URL.revokeObjectURL(url)
}

const EMPTY = {
  ticker: '', side: 'BUY' as TradeSide, quantity: '', price: '', fees: '0',
  trade_datetime: '', rationale: '',
}

export default function Journal() {
  const qc = useQueryClient()
  const [form, setForm] = useState({ ...EMPTY })
  const [formError, setFormError] = useState<string | null>(null)
  const [taxYear, setTaxYear] = useState<string>('')

  const trades = useQuery({ queryKey: ['trades'], queryFn: api.listTrades })
  const tax = useQuery({
    queryKey: ['tax', taxYear],
    queryFn: () => api.getTaxSummary(taxYear ? Number(taxYear) : undefined),
  })

  const add = useMutation({
    mutationFn: () =>
      api.createTrade({
        ticker: form.ticker.trim().toUpperCase(),
        side: form.side,
        quantity: Number(form.quantity),
        price: Number(form.price),
        fees: Number(form.fees || 0),
        trade_datetime: new Date(form.trade_datetime).toISOString(),
        rationale: form.rationale.trim() || null,
      }),
    onSuccess: () => {
      setForm({ ...EMPTY })
      setFormError(null)
      qc.invalidateQueries({ queryKey: ['trades'] })
      qc.invalidateQueries({ queryKey: ['tax'] })
    },
    onError: (e) => setFormError(e instanceof ApiError ? e.message : 'Failed to save.'),
  })

  const del = useMutation({
    mutationFn: (id: number) => api.deleteTrade(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['trades'] })
      qc.invalidateQueries({ queryKey: ['tax'] })
    },
  })

  const onSubmit = (e: FormEvent) => {
    e.preventDefault()
    if (!form.ticker || !form.quantity || !form.price || !form.trade_datetime) {
      setFormError('Ticker, quantity, price and date are required.')
      return
    }
    add.mutate()
  }

  const set = (k: keyof typeof form) => (e: { target: { value: string } }) =>
    setForm((f) => ({ ...f, [k]: e.target.value }))

  return (
    <section>
      <h1>Trade journal</h1>

      <Explainer title="New to this? What the Journal is for">
        <p>This is where <strong>you</strong> record the <strong>real</strong> trades
        you actually made on your exchange (the app can't see your exchange). It keeps
        an honest history and works out your tax numbers.</p>
        <dl>
          <dt>Side (Buy / Sell)</dt>
          <dd>Whether you bought or sold. <strong>Price</strong> is per unit in USD;
          <strong> Fees</strong> is what the exchange charged.</dd>
          <dt>Tax summary</dt>
          <dd>For a chosen tax year it matches your sells against earlier buys
          (<strong>FIFO</strong> = First In, First Out) to work out realised
          <strong> gain/loss</strong> = what you sold for, minus what you originally
          paid, minus fees. <strong>Proceeds</strong> = sale value; <strong>base cost</strong>
          = original purchase cost. Export to CSV for your records.</dd>
        </dl>
        <p className="warn">Record-keeping only, not tax advice. In South Africa crypto
        gains are taxable — confirm your situation with a registered tax practitioner.</p>
      </Explainer>

      <form onSubmit={onSubmit} className="journal-form">
        <input placeholder="Symbol e.g. BTCUSDT" value={form.ticker} onChange={set('ticker')} maxLength={12} style={{ textTransform: 'uppercase', width: '9rem' }} />
        <select value={form.side} onChange={set('side')}>
          <option value="BUY">Buy</option>
          <option value="SELL">Sell</option>
        </select>
        <input type="number" placeholder="Qty (e.g. 0.5)" value={form.quantity} onChange={set('quantity')} style={{ width: '6rem' }} min="0" step="any" />
        <input type="number" placeholder="Price ($)" value={form.price} onChange={set('price')} style={{ width: '7rem' }} step="any" min="0" />
        <input type="number" placeholder="Fees ($)" value={form.fees} onChange={set('fees')} style={{ width: '6rem' }} step="any" min="0" />
        <input type="datetime-local" value={form.trade_datetime} onChange={set('trade_datetime')} />
        <input placeholder="Rationale (optional)" value={form.rationale} onChange={set('rationale')} style={{ flex: 1, minWidth: '10rem' }} maxLength={1000} />
        <button type="submit" disabled={add.isPending}>{add.isPending ? 'Saving…' : 'Log trade'}</button>
      </form>
      {formError && <p className="error" role="alert">{formError}</p>}

      {trades.data && trades.data.items.length > 0 && (
        <table>
          <thead>
            <tr><th>Date</th><th>Ticker</th><th>Side</th><th>Qty</th><th>Price</th><th>Fees</th><th>Rationale</th><th></th></tr>
          </thead>
          <tbody>
            {trades.data.items.map((t) => (
              <tr key={t.id}>
                <td>{new Date(t.trade_datetime).toLocaleDateString()}</td>
                <td><strong>{t.ticker}</strong></td>
                <td>{t.side}</td>
                <td>{t.quantity.toLocaleString(undefined, { maximumFractionDigits: 8 })}</td>
                <td>{rands(t.price)}</td>
                <td>{rands(t.fees)}</td>
                <td>{t.rationale ?? '—'}</td>
                <td><button className="link" onClick={() => del.mutate(t.id)} disabled={del.isPending}>Delete</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {trades.data && trades.data.items.length === 0 && (
        <p className="muted">No trades logged yet.</p>
      )}

      <div className="detail-head" style={{ marginTop: '2rem' }}>
        <h2 className="section-title">Tax summary (SARS crypto record-keeping)</h2>
        <div className="detail-actions">
          <label>Tax year{' '}
            <input type="number" placeholder={String(tax.data?.tax_year ?? '')} value={taxYear}
              onChange={(e) => setTaxYear(e.target.value)} style={{ width: '6rem' }} />
          </label>
          {tax.data && tax.data.disposals.length > 0 && (
            <button onClick={() => downloadTaxCsv(tax.data)}>Export CSV</button>
          )}
        </div>
      </div>

      {tax.data && (
        <>
          <p className="muted">
            {tax.data.tax_year} · {tax.data.period_start} to {tax.data.period_end}
          </p>
          {tax.data.disposals.length === 0 ? (
            <p className="muted">No realised disposals in this tax year.</p>
          ) : (
            <table>
              <thead>
                <tr><th>Ticker</th><th>Sold</th><th>Qty</th><th>Proceeds</th><th>Base cost</th><th>Gain / loss</th></tr>
              </thead>
              <tbody>
                {tax.data.disposals.map((d, i) => (
                  <tr key={i}>
                    <td><strong>{d.ticker}</strong>{d.unmatched_quantity > 0 && <span className="muted"> ({d.unmatched_quantity.toLocaleString(undefined, { maximumFractionDigits: 8 })} unmatched)</span>}</td>
                    <td>{new Date(d.sell_datetime).toLocaleDateString()}</td>
                    <td>{d.quantity.toLocaleString(undefined, { maximumFractionDigits: 8 })}</td>
                    <td>{rands(d.proceeds)}</td>
                    <td>{rands(d.base_cost)}</td>
                    <td className={d.gain >= 0 ? 'pnl-pos' : 'pnl-neg'}>{rands(d.gain)}</td>
                  </tr>
                ))}
                <tr>
                  <td colSpan={3}><strong>Total</strong></td>
                  <td><strong>{rands(tax.data.total_proceeds)}</strong></td>
                  <td><strong>{rands(tax.data.total_base_cost)}</strong></td>
                  <td className={tax.data.total_realised_gain >= 0 ? 'pnl-pos' : 'pnl-neg'}><strong>{rands(tax.data.total_realised_gain)}</strong></td>
                </tr>
              </tbody>
            </table>
          )}
          <p className="disclaimer-inline">{tax.data.disclaimer}</p>
        </>
      )}
    </section>
  )
}
