interface Sub { name: string; detail: string; contribution: number }
interface LayerR { score: number; signals?: Sub[]; [k: string]: unknown }

// Renders the transparent per-layer rationale (§8 — no black-box confidence).
export default function RationaleView({ rationale }: { rationale: Record<string, unknown> | null }) {
  if (!rationale) return <p className="muted">No rationale recorded.</p>
  const tech = rationale.technical as LayerR | undefined
  const macro = rationale.macro as LayerR | undefined
  const sent = rationale.sentiment as LayerR | undefined
  const weights = rationale.weights as Record<string, number> | undefined

  return (
    <div className="rationale">
      {weights && (
        <p className="muted">
          Weights — technical {weights.technical}, macro {weights.macro}, sentiment {weights.sentiment}
        </p>
      )}

      <div className="rationale-layer">
        <strong>Technical ({tech?.score ?? '—'})</strong>
        <ul>
          {(tech?.signals ?? []).map((s, i) => (
            <li key={i}>{s.detail} <span className="muted">({s.contribution >= 0 ? '+' : ''}{s.contribution})</span></li>
          ))}
          {!tech?.signals?.length && <li className="muted">no sub-signals fired</li>}
        </ul>
      </div>

      <div className="rationale-layer">
        <strong>Macro ({macro?.score ?? '—'})</strong>
        <p className="muted">Regime: {(macro?.regime as string) ?? '—'}
          {macro?.sector ? ` · sector ${macro.sector} tilt ${macro.sector_tilt}` : ''}</p>
      </div>

      <div className="rationale-layer">
        <strong>Sentiment ({sent?.score ?? '—'})</strong>
        <p className="muted">
          {(sent?.article_count as number) ?? 0} article(s)
          {sent?.mean_sentiment !== undefined ? ` · mean ${sent.mean_sentiment}` : ''}
        </p>
      </div>
    </div>
  )
}
