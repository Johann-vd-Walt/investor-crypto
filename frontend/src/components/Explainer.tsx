import { type ReactNode } from 'react'

// A collapsible, plain-language help panel for beginners. Uses native <details>
// so it's accessible and needs no state.
export default function Explainer({
  title = 'New to this? Click for a plain-language guide',
  children,
}: {
  title?: string
  children: ReactNode
}) {
  return (
    <details className="explainer">
      <summary>💡 {title}</summary>
      <div className="explainer-body">{children}</div>
    </details>
  )
}
