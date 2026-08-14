import { useEffect, useState, type ReactNode, type FormEvent } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api, ApiError, setToken } from '../api/client'

function Login({ onSuccess }: { onSuccess: () => void }) {
  const [code, setCode] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const { token } = await api.login(code.trim())
      setToken(token)
      onSuccess()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Login failed.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="login-wrap">
      <div className="login-card">
        <h1 className="brand">Crypto Swing-Trader</h1>
        <p className="muted">Enter the 6-digit code from your authenticator app.</p>
        <form onSubmit={submit}>
          <input
            className="login-code"
            inputMode="numeric"
            autoComplete="one-time-code"
            placeholder="000000"
            maxLength={6}
            value={code}
            onChange={(e) => setCode(e.target.value.replace(/\D/g, ''))}
            autoFocus
          />
          <button type="submit" disabled={busy || code.length < 6}>
            {busy ? 'Checking…' : 'Unlock'}
          </button>
        </form>
        {error && <p className="error" role="alert">{error}</p>}
      </div>
    </div>
  )
}

// Gates the whole app behind the TOTP login when the backend has it enabled.
export default function AuthGate({ children }: { children: ReactNode }) {
  const status = useQuery({ queryKey: ['auth-status'], queryFn: api.getAuthStatus, retry: false })

  useEffect(() => {
    const onAuthRequired = () => status.refetch()
    window.addEventListener('auth-required', onAuthRequired)
    return () => window.removeEventListener('auth-required', onAuthRequired)
  }, [status])

  if (status.isLoading) return <div className="login-wrap"><p className="muted">Loading…</p></div>
  const data = status.data
  if (data && data.enabled && !data.authenticated) {
    return <Login onSuccess={() => status.refetch()} />
  }
  return <>{children}</>
}
