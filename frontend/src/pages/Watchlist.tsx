import { useState, type FormEvent } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { api, ApiError } from '../api/client'
import Explainer from '../components/Explainer'

export default function Watchlist() {
  const qc = useQueryClient()
  const [ticker, setTicker] = useState('')
  const [notes, setNotes] = useState('')
  const [formError, setFormError] = useState<string | null>(null)

  const watchlist = useQuery({
    queryKey: ['watchlist'],
    queryFn: api.listWatchlist,
  })

  const addMutation = useMutation({
    mutationFn: () => api.addWatchlist(ticker.trim().toUpperCase(), notes.trim()),
    onSuccess: () => {
      setTicker('')
      setNotes('')
      setFormError(null)
      qc.invalidateQueries({ queryKey: ['watchlist'] })
    },
    onError: (err) => {
      setFormError(err instanceof ApiError ? err.message : 'Failed to add.')
    },
  })

  const removeMutation = useMutation({
    mutationFn: (id: number) => api.removeWatchlist(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['watchlist'] }),
  })

  const onSubmit = (e: FormEvent) => {
    e.preventDefault()
    if (!ticker.trim()) {
      setFormError('Enter a ticker.')
      return
    }
    addMutation.mutate()
  }

  return (
    <section>
      <h1>Watchlist</h1>

      <Explainer title="New to this? What is the Watchlist for?">
        <p>Your shortlist of coins to follow. Adding a symbol (e.g. <code>BTCUSDT</code>)
        tells the app's background updater to keep its prices and signals fresh, and
        gives you quick links to each one. It does <strong>not</strong> buy anything —
        this app never places trades.</p>
        <p><strong>Notes</strong> is just a free-text reminder to yourself (e.g. "watching
        for a dip"). Remove a coin any time.</p>
      </Explainer>

      <form onSubmit={onSubmit} className="add-form">
        <input
          aria-label="Symbol"
          placeholder="Symbol (e.g. BTCUSDT)"
          value={ticker}
          onChange={(e) => setTicker(e.target.value)}
          maxLength={12}
        />
        <input
          aria-label="Notes"
          placeholder="Notes (optional)"
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          maxLength={500}
        />
        <button type="submit" disabled={addMutation.isPending}>
          {addMutation.isPending ? 'Adding…' : 'Add'}
        </button>
      </form>
      {formError && <p className="error" role="alert">{formError}</p>}

      {watchlist.isLoading && <p>Loading…</p>}
      {watchlist.isError && (
        <p className="error" role="alert">
          Could not load the watchlist. Is the backend running?
        </p>
      )}

      {watchlist.data && watchlist.data.length === 0 && (
        <p>No securities on the watchlist yet. Add one above.</p>
      )}

      {watchlist.data && watchlist.data.length > 0 && (
        <table>
          <thead>
            <tr>
              <th>Ticker</th>
              <th>Name</th>
              <th>Sector</th>
              <th>Notes</th>
              <th>Added</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {watchlist.data.map((item) => (
              <tr key={item.id}>
                <td>
                  <Link to={`/security/${item.security.ticker}`}>
                    <strong>{item.security.ticker}</strong>
                  </Link>
                </td>
                <td>{item.security.name}</td>
                <td>{item.security.sector ?? '—'}</td>
                <td>{item.notes ?? '—'}</td>
                <td>{new Date(item.added_at).toLocaleDateString()}</td>
                <td>
                  <button
                    className="link"
                    onClick={() => removeMutation.mutate(item.id)}
                    disabled={removeMutation.isPending}
                  >
                    Remove
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  )
}
