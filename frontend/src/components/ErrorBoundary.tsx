import { Component, type ReactNode } from 'react'

interface Props { children: ReactNode }
interface State { error: Error | null }

// Graceful degradation (§9): a render error in one page shows a message instead
// of white-screening the whole app.
export default class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  componentDidCatch(error: Error) {
    console.error('Render error caught by ErrorBoundary:', error)
  }

  render() {
    if (this.state.error) {
      return (
        <div className="banner banner-warn" role="alert" style={{ margin: '1rem 0' }}>
          <strong>Something went wrong rendering this page.</strong>
          <div style={{ fontSize: '0.8rem', marginTop: '0.3rem' }}>
            {this.state.error.message}
          </div>
          <button style={{ marginTop: '0.6rem' }} onClick={() => this.setState({ error: null })}>
            Try again
          </button>
        </div>
      )
    }
    return this.props.children
  }
}
