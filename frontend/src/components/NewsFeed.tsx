import type { NewsArticle } from '../api/client'
import { fmtDateTime } from '../format'

function SentimentBadge({ score }: { score: number | null }) {
  if (score === null || score === undefined) return null
  // Marketaux sentiment is on a -1..1 scale.
  const cls = score > 0.15 ? 'pos' : score < -0.15 ? 'neg' : 'neu'
  const label = cls === 'pos' ? 'positive' : cls === 'neg' ? 'negative' : 'neutral'
  return (
    <span className={`sentiment sentiment--${cls}`} title={`sentiment ${score.toFixed(2)}`}>
      {label} {score.toFixed(2)}
    </span>
  )
}

interface Props {
  articles: NewsArticle[]
  isLoading?: boolean
  isError?: boolean
  emptyHint?: string
}

export default function NewsFeed({ articles, isLoading, isError, emptyHint }: Props) {
  if (isLoading) return <p>Loading news…</p>
  if (isError) return <p className="error" role="alert">Could not load news.</p>
  if (!articles.length) {
    return <p className="muted">{emptyHint ?? 'No news yet.'}</p>
  }

  return (
    <ul className="news-list">
      {articles.map((a) => (
        <li key={a.id} className="news-item">
          <div className="news-head">
            <a href={a.url} target="_blank" rel="noopener noreferrer">{a.title}</a>
            <SentimentBadge score={a.sentiment} />
          </div>
          <div className="news-meta">
            {a.source}
            {a.published_at ? ` · ${fmtDateTime(a.published_at)}` : ''}
          </div>
          {a.snippet && <p className="news-snippet">{a.snippet}</p>}
        </li>
      ))}
    </ul>
  )
}
