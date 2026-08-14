// Shared display formatting for crypto (quote currency = USDT, shown as $).

export function usd(n: number | null | undefined): string {
  if (n === null || n === undefined) return '—'
  const abs = Math.abs(n)
  const dp = abs >= 1 ? 2 : abs >= 0.01 ? 4 : 8
  return `$${n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: dp })}`
}
