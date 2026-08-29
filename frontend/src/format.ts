// Shared display formatting for crypto (quote currency = USDT, shown as $).

export function usd(n: number | null | undefined): string {
  if (n === null || n === undefined) return '—'
  const abs = Math.abs(n)
  const dp = abs >= 1 ? 2 : abs >= 0.01 ? 4 : 8
  return `$${n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: dp })}`
}

// --- Time (SAST) ------------------------------------------------------------
// The backend sends naive-UTC ISO strings (no offset), because the server runs
// on UTC. Left to itself, `new Date()` reads a marker-less string as the
// browser's local time, so the UTC wall-clock value shows verbatim — 2h behind
// in SA. We therefore stamp missing offsets as UTC and always render in SAST,
// so the displayed time is correct regardless of the viewer's own timezone.

const SAST = 'Africa/Johannesburg'

function toInstant(value: string | number | Date): Date {
  if (value instanceof Date) return value
  if (typeof value === 'number') return new Date(value)
  // Already carries a zone (Z or ±hh:mm)? Trust it. Otherwise it's naive UTC.
  const hasZone = /(?:z|[+-]\d{2}:?\d{2})$/i.test(value)
  return new Date(hasZone ? value : value + 'Z')
}

/** Date + time in SAST, e.g. "2026/08/29, 13:26:10". */
export function fmtDateTime(value: string | number | Date | null | undefined): string {
  if (value === null || value === undefined || value === '') return '—'
  return toInstant(value).toLocaleString(undefined, { timeZone: SAST })
}

/** Time only in SAST, e.g. "13:26:10". */
export function fmtTime(value: string | number | Date | null | undefined): string {
  if (value === null || value === undefined || value === '') return '—'
  return toInstant(value).toLocaleTimeString(undefined, { timeZone: SAST })
}

/** Date only in SAST, e.g. "2026/08/29". */
export function fmtDate(value: string | number | Date | null | undefined): string {
  if (value === null || value === undefined || value === '') return '—'
  return toInstant(value).toLocaleDateString(undefined, { timeZone: SAST })
}
