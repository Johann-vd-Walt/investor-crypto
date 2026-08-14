import { useEffect, useRef } from 'react'
import {
  createChart,
  CandlestickSeries,
  LineSeries,
  HistogramSeries,
  type IChartApi,
  type CandlestickData,
  type LineData,
  type HistogramData,
  type UTCTimestamp,
} from 'lightweight-charts'
import type { PriceBar } from '../api/client'

interface Props {
  bars: PriceBar[]
}

const t = (b: PriceBar) => Math.floor(Date.parse(b.bar_datetime) / 1000) as UTCTimestamp

// Simple moving average over close, emitted once enough history exists.
function sma(bars: PriceBar[], n: number): LineData[] {
  const out: LineData[] = []
  let sum = 0
  for (let i = 0; i < bars.length; i++) {
    sum += bars[i].close
    if (i >= n) sum -= bars[i - n].close
    if (i >= n - 1) out.push({ time: t(bars[i]), value: sum / n })
  }
  return out
}

// Candlesticks (Rand) + SMA20/SMA50 overlays + a volume pane.
export default function CandlestickChart({ bars }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)

  useEffect(() => {
    if (!containerRef.current) return

    const chart = createChart(containerRef.current, {
      layout: { background: { color: 'transparent' }, textColor: '#8b949e' },
      grid: { vertLines: { color: '#21262d' }, horzLines: { color: '#21262d' } },
      rightPriceScale: { borderColor: '#30363d', scaleMargins: { top: 0.05, bottom: 0.25 } },
      timeScale: { borderColor: '#30363d' },
      crosshair: { mode: 0 },
      // autoSize sizes the chart to its container; the container MUST have a
      // fixed height (set on the div below) or the chart grows unbounded.
      autoSize: true,
    })
    chartRef.current = chart

    const candles = chart.addSeries(CandlestickSeries, {
      upColor: '#3fb950', downColor: '#f85149', borderVisible: false,
      wickUpColor: '#3fb950', wickDownColor: '#f85149',
    })
    candles.setData(
      bars.map((b): CandlestickData => ({
        time: t(b), open: b.open, high: b.high, low: b.low, close: b.close,
      })),
    )

    if (bars.length >= 20) {
      const sma20 = chart.addSeries(LineSeries, { color: '#58a6ff', lineWidth: 1, priceLineVisible: false, lastValueVisible: false })
      sma20.setData(sma(bars, 20))
    }
    if (bars.length >= 50) {
      const sma50 = chart.addSeries(LineSeries, { color: '#d29922', lineWidth: 1, priceLineVisible: false, lastValueVisible: false })
      sma50.setData(sma(bars, 50))
    }

    // Volume pane pinned to the bottom.
    const vol = chart.addSeries(HistogramSeries, {
      priceScaleId: 'vol', priceFormat: { type: 'volume' }, lastValueVisible: false,
    })
    chart.priceScale('vol').applyOptions({ scaleMargins: { top: 0.8, bottom: 0 } })
    vol.setData(
      bars.map((b): HistogramData => ({
        time: t(b),
        value: b.volume ?? 0,
        color: b.close >= b.open ? 'rgba(63,185,80,0.45)' : 'rgba(248,81,73,0.45)',
      })),
    )

    chart.timeScale().fitContent()
    return () => {
      chart.remove()
      chartRef.current = null
    }
  }, [bars])

  return (
    <>
      <div ref={containerRef} style={{ width: '100%', height: 420 }} />
      <p className="muted" style={{ fontSize: '0.72rem' }}>
        <span style={{ color: '#58a6ff' }}>— SMA20</span>{'  '}
        <span style={{ color: '#d29922' }}>— SMA50</span>{'  '}· volume below
      </p>
    </>
  )
}
