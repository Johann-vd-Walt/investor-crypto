import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'
import Explainer from '../components/Explainer'

export default function PineScript() {
  const pine = useQuery({ queryKey: ['pinescript'], queryFn: api.getPineScript })
  const [copied, setCopied] = useState(false)

  const copy = async () => {
    if (!pine.data) return
    try {
      await navigator.clipboard.writeText(pine.data.pine)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      setCopied(false)
    }
  }

  return (
    <section>
      <h1>Pine Script (TradingView)</h1>
      <p className="muted">
        Generates a TradingView strategy that mirrors the app's <strong>technical</strong>
        backtest, using your current Settings. Paste it into TradingView to compare
        against the app's backtest.
      </p>

      <Explainer title="New to this? What is Pine Script / TradingView?">
        <p><strong>TradingView</strong> is a popular free charting website.
        <strong> Pine Script</strong> is its little programming language for strategies.
        This page writes a Pine script for you that copies the app's technical strategy,
        so you can paste it into TradingView and see the same idea tested there — an
        independent second opinion.</p>
        <p>You don't need to code anything: click <strong>Copy script</strong>, follow
        the steps below in TradingView, and read its "Strategy Tester". The two won't
        match exactly (different data and fees) — look for broad agreement, not identical
        numbers.</p>
      </Explainer>

      <div className="banner banner-info">
        This reproduces the <strong>technical strategy only</strong> (macro / sentiment /
        momentum aren't single-symbol constructs). TradingView uses its own JSE data
        feed, so expect the same <em>direction</em>, not identical numbers.
      </div>

      {pine.isLoading && <p>Generating…</p>}
      {pine.isError && <p className="error" role="alert">Could not generate the script.</p>}

      {pine.data && (
        <>
          <div className="detail-head">
            <h2 className="section-title">Parameters (from Settings)</h2>
            <button onClick={copy}>{copied ? 'Copied ✓' : 'Copy script'}</button>
          </div>
          <div className="signal-metrics">
            {Object.entries(pine.data.params).map(([k, v]) => (
              <span key={k}>{k}: <strong>{v}</strong></span>
            ))}
          </div>

          <pre className="pine-code">{pine.data.pine}</pre>

          <h2 className="section-title">How to use it</h2>
          <ol className="pine-steps">
            <li>In TradingView, open a crypto chart — e.g. <code>BINANCE:BTCUSDT</code>, <code>BINANCE:ETHUSDT</code>.</li>
            <li>Set the timeframe to <strong>Daily (1D)</strong>.</li>
            <li>Open <strong>Pine Editor</strong> (bottom), paste the script, click <strong>Add to chart</strong>.</li>
            <li>Open the <strong>Strategy Tester</strong> tab to see performance; set the date range to match your app backtest.</li>
          </ol>

          <h2 className="section-title">Read the comparison honestly</h2>
          <ul className="pine-steps">
            {pine.data.notes.map((n, i) => <li key={i}>{n}</li>)}
          </ul>
          <p className="disclaimer-inline">
            If TradingView looks great but the app's cost-and-benchmark-honest backtest
            says the strategy lags buy-and-hold, trust the disagreement — that's the
            point of running both.
          </p>
        </>
      )}
    </section>
  )
}
