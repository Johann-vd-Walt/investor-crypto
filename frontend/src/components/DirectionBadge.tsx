import type { SignalDirection } from '../api/client'

export default function DirectionBadge({ direction }: { direction: SignalDirection }) {
  const cls =
    direction === 'BUY' ? 'dir--buy' : direction === 'SELL' ? 'dir--sell' : 'dir--hold'
  return <span className={`dir ${cls}`}>{direction}</span>
}
