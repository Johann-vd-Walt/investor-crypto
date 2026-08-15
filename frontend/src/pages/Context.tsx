import { useQuery } from '@tanstack/react-query'
import { api, type MacroSnapshotItem } from '../api/client'
import Explainer from '../components/Explainer'

type Group = { title: string; blurb: string; codes: string[] }

const GROUPS: Group[] = [
  {
    title: 'Liquidity — “dry powder” & demand',
    blurb: 'How much money is sitting ready to buy, and whether institutions are buying. Rising = supportive backdrop; falling = de-risking. Slow-moving (weeks–months), not an entry trigger.',
    codes: ['STABLE', 'ETF_FLOW'],
  },
  {
    title: 'Valuation & sentiment — cycle extremes',
    blurb: 'Where the market sits versus its own history. Informative mainly at extremes (very cheap / very euphoric), not in the middle.',
    codes: ['MVRV', 'FNG'],
  },
  {
    title: 'Macro regime — the tide crypto swims in',
    blurb: 'Dollar, rates, gold and equities. Crypto’s correlation with these is real but regime-dependent and unstable — use it to avoid fighting the tide, not to time entries.',
    codes: ['DXY', 'US10Y', 'SP500', 'GOLD'],
  },
]

function fmt(item: MacroSnapshotItem): string {
  if (!item.available || item.value == null) return '—'
  const v = item.value
  const abs = Math.abs(v)
  const num = abs >= 1000 ? v.toLocaleString(undefined, { maximumFractionDigits: 0 })
    : v.toLocaleString(undefined, { maximumFractionDigits: 2 })
  return item.unit ? `${num} ${item.unit}` : num
}

export default function Context() {
  const q = useQuery({ queryKey: ['macro'], queryFn: api.getMacroSnapshot })
  const byCode = new Map((q.data?.items ?? []).map((i) => [i.series_code, i]))

  return (
    <section>
      <h1>Market Context</h1>

      <Explainer title="How should I read this page?">
        <p>These are <strong>backdrop</strong> indicators, not buy/sell signals. Research is
        clear that on a swing horizon (days–weeks) none of them reliably leads price. Their job
        is to <strong>filter</strong> — don’t fight a shrinking-liquidity, risk-off tide — and to
        <strong> flag cycle extremes</strong>. The app never trades for you.</p>
        <p>Some series need a free API key to switch on (they say so below). The keyless ones —
        stablecoin supply and Fear &amp; Greed — work out of the box.</p>
      </Explainer>

      {q.isLoading && <p>Loading…</p>}
      {q.isError && <p className="error" role="alert">Could not load context. Is the backend running?</p>}

      {q.data && GROUPS.map((g) => (
        <div key={g.title} style={{ marginBottom: '1.5rem' }}>
          <h2 style={{ marginBottom: '0.25rem' }}>{g.title}</h2>
          <p style={{ color: '#94a3b8', marginTop: 0, fontSize: '0.9rem' }}>{g.blurb}</p>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: '0.75rem' }}>
            {g.codes.map((code) => {
              const item = byCode.get(code)
              if (!item) return null
              return (
                <div key={code} style={{ border: '1px solid #334155', borderRadius: 8, padding: '0.75rem', opacity: item.available ? 1 : 0.6 }}>
                  <div style={{ color: '#94a3b8', fontSize: '0.8rem' }}>{item.label}</div>
                  <div style={{ fontSize: '1.4rem', fontWeight: 600 }}>{fmt(item)}</div>
                  {item.available && item.as_of && (
                    <div style={{ color: '#64748b', fontSize: '0.75rem' }}>as of {item.as_of}{item.source ? ` · ${item.source}` : ''}</div>
                  )}
                  {!item.available && (
                    <div style={{ color: '#f59e0b', fontSize: '0.75rem', marginTop: '0.25rem' }}>{item.note}</div>
                  )}
                </div>
              )
            })}
          </div>
        </div>
      ))}

      <p style={{ color: '#64748b', fontSize: '0.85rem' }}>
        Context only. Correlations shift and break; treat every tile as a slow-moving backdrop,
        never a standalone reason to act.
      </p>
    </section>
  )
}
