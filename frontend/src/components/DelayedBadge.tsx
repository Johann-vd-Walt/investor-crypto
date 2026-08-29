interface Props {
  isDelayed: boolean
  asOf: string | null
  source?: string | null
}

// Every screen showing prices must display as_of + a clear delayed badge (§12,
// Guardrail 2.7). Never present stale data as if it were live.
import { fmtDate } from '../format'

export default function DelayedBadge({ isDelayed, asOf, source }: Props) {
  const asOfText = asOf ? fmtDate(asOf) : 'no data'
  return (
    <span className="freshness">
      {isDelayed && <span className="badge badge-delayed">DELAYED</span>}
      <span className="asof">
        as of {asOfText}
        {source ? ` · ${source}` : ''}
      </span>
    </span>
  )
}
