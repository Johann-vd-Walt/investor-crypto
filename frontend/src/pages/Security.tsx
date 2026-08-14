import { useQuery } from '@tanstack/react-query'
import { api, type AuthEventType } from '../api/client'
import Explainer from '../components/Explainer'

const LABEL: Record<AuthEventType, string> = {
  success: '✓ Signed in',
  failed: '✗ Wrong code',
  locked: '⛔ Rate-limited',
}

export default function Security() {
  const log = useQuery({
    queryKey: ['access-log'],
    queryFn: () => api.getAccessLog(200),
    refetchInterval: 60 * 1000, // refresh every minute
  })

  const s = log.data?.summary

  return (
    <section>
      <h1>Security · Access Log</h1>

      <Explainer title="What am I looking at?">
        <p>Every attempt to sign in to <strong>this app</strong> is recorded here — successful
        logins, wrong codes, and attempts that were blocked for hitting the rate limit. Use it
        to spot if someone other than you is trying to get in.</p>
        <p>A handful of <em>Wrong code</em> lines from your own IP is usually just a mistyped
        code. Many failures from IP addresses you don't recognise means someone is probing the
        login — they still can't get in without your authenticator, and after 6 failures in 5
        minutes an IP is blocked automatically.</p>
        <p>This tracks the <strong>app</strong> login only. Attempts to break into the
        <strong> server itself</strong> (SSH) are handled separately by the server's firewall
        and fail2ban, and aren't shown here.</p>
      </Explainer>

      {log.isLoading && <p>Loading…</p>}
      {log.isError && (
        <p className="error" role="alert">Could not load the access log. Is the backend running?</p>
      )}

      {s && (
        <div className="banner" role="status" style={{ marginBottom: '1rem' }}>
          <strong>Last {s.window_hours}h:</strong>{' '}
          {s.success} sign-in{s.success === 1 ? '' : 's'},{' '}
          <strong>{s.failed}</strong> failed{s.locked > 0 && <> , {s.locked} rate-limited</>}
          {s.distinct_failed_ips > 0 && (
            <> — from <strong>{s.distinct_failed_ips}</strong> distinct IP
            {s.distinct_failed_ips === 1 ? '' : 's'}</>
          )}
          {s.failed === 0 && s.locked === 0 && ' — nothing suspicious.'}
        </div>
      )}

      {log.data && log.data.events.length === 0 && (
        <p>No login attempts recorded yet.</p>
      )}

      {log.data && log.data.events.length > 0 && (
        <table>
          <thead>
            <tr>
              <th>When</th>
              <th>Outcome</th>
              <th>IP address</th>
              <th>Device / browser</th>
            </tr>
          </thead>
          <tbody>
            {log.data.events.map((e) => (
              <tr key={e.id}>
                <td>{new Date(e.created_at).toLocaleString()}</td>
                <td>{LABEL[e.event] ?? e.event}</td>
                <td><code>{e.ip ?? '—'}</code></td>
                <td style={{ maxWidth: 380, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={e.user_agent ?? ''}>
                  {e.user_agent ?? '—'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  )
}
