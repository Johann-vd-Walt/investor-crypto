import { useQuery } from '@tanstack/react-query'
import { BrowserRouter, Link, NavLink, Route, Routes } from 'react-router-dom'
import { api, clearToken } from './api/client'
import Dashboard from './pages/Dashboard'
import Securities from './pages/Securities'
import Watchlist from './pages/Watchlist'
import Signals from './pages/Signals'
import Positioning from './pages/Positioning'
import Context from './pages/Context'
import Consensus from './pages/Consensus'
import PaperPerformance from './pages/PaperPerformance'
import Journal from './pages/Journal'
import Backtest from './pages/Backtest'
import PineScript from './pages/PineScript'
import Settings from './pages/Settings'
import Security from './pages/Security'
import SecurityDetail from './pages/SecurityDetail'
import ErrorBoundary from './components/ErrorBoundary'
import './App.css'

function DataFreshnessBanner() {
  const health = useQuery({ queryKey: ['health'], queryFn: api.health })
  const freshness = useQuery({
    queryKey: ['freshness'],
    queryFn: api.getFreshness,
    refetchInterval: 5 * 60 * 1000,
  })

  if (health.isError || health.data?.status !== 'ok') {
    return (
      <div className="banner banner-warn" role="status">
        Backend degraded — data may be unavailable or stale.
        {health.data?.database.connected === false && ' Database is unreachable.'}
      </div>
    )
  }

  const staleNames = freshness.data?.families.filter((f) => f.stale && f.count > 0).map((f) => f.name)
  if (staleNames && staleNames.length > 0) {
    return (
      <div className="banner banner-warn" role="status">
        Data may be stale — no recent ingest for: <strong>{staleNames.join(', ')}</strong>.
        Run the relevant job (or check the scheduler) to refresh.
      </div>
    )
  }
  return null
}

function LogoutButton() {
  const status = useQuery({ queryKey: ['auth-status'], queryFn: api.getAuthStatus, retry: false })
  if (!status.data?.enabled) return null
  return (
    <button
      className="link"
      style={{ marginLeft: 'auto' }}
      onClick={() => { clearToken(); window.location.reload() }}
    >
      Lock
    </button>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <div className="app">
        <header className="app-header">
          <Link to="/" className="brand-link">
            <h1 className="brand">Crypto Swing-Trader</h1>
          </Link>
          <span className="tag">decision-support only · not a broker · not financial advice</span>
          <LogoutButton />
        </header>

        <nav className="app-nav">
          <NavLink to="/" end>Dashboard</NavLink>
          <NavLink to="/securities">Markets</NavLink>
          <NavLink to="/watchlist">Watchlist</NavLink>
          <NavLink to="/signals">Signals</NavLink>
          <NavLink to="/positioning">Positioning</NavLink>
          <NavLink to="/context">Context</NavLink>
          <NavLink to="/consensus">Consensus</NavLink>
          <NavLink to="/paper">Paper</NavLink>
          <NavLink to="/journal">Journal</NavLink>
          <NavLink to="/backtest">Backtest</NavLink>
          <NavLink to="/pinescript">Pine</NavLink>
          <NavLink to="/settings">Settings</NavLink>
          <NavLink to="/security">Security</NavLink>
        </nav>

        <DataFreshnessBanner />

        <main className="app-main">
          <ErrorBoundary>
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/securities" element={<Securities />} />
            <Route path="/watchlist" element={<Watchlist />} />
            <Route path="/signals" element={<Signals />} />
            <Route path="/positioning" element={<Positioning />} />
            <Route path="/context" element={<Context />} />
            <Route path="/consensus" element={<Consensus />} />
            <Route path="/paper" element={<PaperPerformance />} />
            <Route path="/journal" element={<Journal />} />
            <Route path="/backtest" element={<Backtest />} />
            <Route path="/pinescript" element={<PineScript />} />
            <Route path="/settings" element={<Settings />} />
            <Route path="/security" element={<Security />} />
            <Route path="/security/:ticker" element={<SecurityDetail />} />
          </Routes>
          </ErrorBoundary>
        </main>

        <footer className="app-footer">
          This is a personal decision-support tool, not financial, tax, or legal
          advice, and not a broker/exchange. It does not place trades. Crypto is
          highly volatile and you can lose your entire capital. Signals are
          probabilistic estimates and are frequently wrong. In South Africa,
          crypto-asset gains are taxable (income or CGT depending on your
          activity) — confirm with a registered tax practitioner.
        </footer>
      </div>
    </BrowserRouter>
  )
}
