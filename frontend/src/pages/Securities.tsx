import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import Explainer from '../components/Explainer'

// Browse / search the full securities universe and drill into any name.
export default function Securities() {
  const [query, setQuery] = useState('')

  const results = useQuery({
    queryKey: ['securities', query],
    queryFn: () => api.listSecurities({ query: query.trim() || undefined, limit: 100 }),
  })

  return (
    <section>
      <h1>Markets</h1>
      <p className="muted">Search any crypto market by symbol or name, then click through for price history, charts and news.</p>

      <Explainer title="New to this? What is a 'market' / symbol?">
        <p>Each row is a tradable pair. The <strong>symbol</strong> combines the coin
        and the currency it's priced in:</p>
        <ul>
          <li><code>BTCUSDT</code> = <strong>B</strong>i<strong>TC</strong>oin priced
          in <strong>USDT</strong> (a US-dollar stablecoin). So it's "the dollar price
          of Bitcoin".</li>
          <li><code>ETHUSDT</code> = Ethereum in USDT, and so on.</li>
        </ul>
        <p><strong>Category</strong> is a rough grouping (e.g. "Layer 1" = a base
        blockchain like Bitcoin/Ethereum; "Meme" = joke/community coins; "DeFi" =
        decentralised finance). Click a symbol to see its chart, indicators and the
        app's current signal.</p>
      </Explainer>

      <div className="filters">
        <input
          aria-label="Search markets"
          placeholder="Search symbol or name (e.g. BTC, Ethereum, Solana)…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          style={{ width: '22rem' }}
          autoFocus
        />
      </div>

      {results.isLoading && <p>Loading…</p>}
      {results.isError && <p className="error" role="alert">Could not load markets.</p>}

      {results.data && (
        <>
          <p className="muted">{results.data.total} match{results.data.total === 1 ? '' : 'es'}{results.data.total > results.data.items.length ? ` (showing ${results.data.items.length})` : ''}</p>
          <table>
            <thead>
              <tr><th>Symbol</th><th>Name</th><th>Category</th></tr>
            </thead>
            <tbody>
              {results.data.items.map((s) => (
                <tr key={s.id}>
                  <td><Link to={`/security/${s.ticker}`}><strong>{s.ticker}</strong></Link></td>
                  <td>{s.name}</td>
                  <td>{s.sector ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </section>
  )
}
