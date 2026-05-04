import { forwardRef, useEffect, useImperativeHandle, useMemo, useRef, useState, type ReactNode } from 'react'
import {
  CandlestickSeries,
  HistogramSeries,
  LineStyle,
  createChart,
  createSeriesMarkers,
  type IChartApi,
  type ISeriesApi,
  type SeriesMarker,
  type UTCTimestamp,
} from 'lightweight-charts'

import type { CandleBar } from '@/api/client'

export interface ForexChartPriceLine {
  price: number
  title: string
  color: string
  lineStyle?: LineStyle
}

export interface ForexChartMarker {
  timestamp: string
  position: 'aboveBar' | 'belowBar' | 'inBar'
  shape: 'arrowUp' | 'arrowDown' | 'circle' | 'square'
  color: string
  text?: string
  payload?: unknown
}

interface ForexChartProps {
  candles: CandleBar[]
  priceLines?: ForexChartPriceLine[]
  markers?: ForexChartMarker[]
  ranges?: number[]
  initialRange?: number
  controls?: ReactNode
  onMarkerSelect?: (marker: ForexChartMarker) => void
}

export interface ForexChartHandle {
  captureImage: () => string | null
  resetView: () => void
}

function pad2(value: number): string {
  return String(value).padStart(2, '0')
}

function formatRawUtcTime(seconds: number): string {
  const date = new Date(seconds * 1000)
  return `${pad2(date.getUTCHours())}:${pad2(date.getUTCMinutes())}`
}

export const ForexChart = forwardRef<ForexChartHandle, ForexChartProps>(function ForexChart({
  candles,
  priceLines = [],
  markers = [],
  ranges = [20, 50, 100],
  initialRange = 100,
  controls = null,
  onMarkerSelect,
}: ForexChartProps, ref) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const seriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null)
  const volumeRef = useRef<ISeriesApi<'Histogram'> | null>(null)
  const markerPrimitiveRef = useRef<{ setMarkers: (markers: SeriesMarker<UTCTimestamp>[]) => void } | null>(null)
  const priceLineRefs = useRef<Array<ReturnType<ISeriesApi<'Candlestick'>['createPriceLine']>>>([])
  const orderedRef = useRef<CandleBar[]>([])
  const markersRef = useRef<ForexChartMarker[]>([])
  const onMarkerSelectRef = useRef<typeof onMarkerSelect>(onMarkerSelect)
  const [range, setRange] = useState(initialRange)
  const [resetNonce, setResetNonce] = useState(0)
  const [hovered, setHovered] = useState<CandleBar | null>(null)
  const orderedCandles = useMemo(
    () => [...candles].sort(
      (left, right) => new Date(left.timestamp).getTime() - new Date(right.timestamp).getTime(),
    ),
    [candles],
  )

  useEffect(() => {
    orderedRef.current = orderedCandles
  }, [orderedCandles])

  useEffect(() => {
    markersRef.current = markers
  }, [markers])

  useEffect(() => {
    onMarkerSelectRef.current = onMarkerSelect
  }, [onMarkerSelect])

  useImperativeHandle(ref, () => ({
    captureImage: () => {
      const chart = chartRef.current as (IChartApi & { takeScreenshot?: (addTopLayer?: boolean, includeCrosshair?: boolean) => HTMLCanvasElement }) | null
      const screenshot = chart?.takeScreenshot?.(true, true)
      return screenshot ? screenshot.toDataURL('image/png') : null
    },
    resetView: () => {
      setRange(initialRange)
      setResetNonce(value => value + 1)
    },
  }), [])

  useEffect(() => {
    const el = containerRef.current
    if (!el) return

    const chart = createChart(el, {
      width: el.clientWidth,
      height: el.clientHeight || 320,
      layout: {
        background: { color: '#111827' },
        textColor: '#9ca3af',
      },
      localization: {
        timeFormatter: (time: unknown) => formatRawUtcTime(Number(time)),
      },
      grid: {
        vertLines: { color: '#1f2937' },
        horzLines: { color: '#1f2937' },
      },
      handleScroll: {
        mouseWheel: true,
        pressedMouseMove: true,
        horzTouchDrag: true,
        vertTouchDrag: true,
      },
      handleScale: {
        mouseWheel: true,
        pinch: true,
        axisPressedMouseMove: {
          time: true,
          price: true,
        },
        axisDoubleClickReset: true,
      },
      timeScale: {
        borderColor: '#374151',
        timeVisible: true,
        secondsVisible: false,
        tickMarkFormatter: (time: unknown) => formatRawUtcTime(Number(time)),
      },
      rightPriceScale: {
        borderColor: '#374151',
      },
      crosshair: {
        vertLine: { color: '#4b5563' },
        horzLine: { color: '#4b5563' },
      },
    })

    const series = chart.addSeries(CandlestickSeries, {
      upColor: '#10b981',
      downColor: '#ef4444',
      borderVisible: false,
      wickUpColor: '#10b981',
      wickDownColor: '#ef4444',
      priceFormat: {
        type: 'price',
        precision: 5,
        minMove: 0.00001,
      },
    })
    const volume = chart.addSeries(HistogramSeries, {
      priceFormat: { type: 'volume' },
      priceScaleId: 'volume',
    })
    chart.priceScale('right').applyOptions({
      scaleMargins: { top: 0.08, bottom: 0.32 },
    })
    chart.priceScale('volume').applyOptions({
      scaleMargins: { top: 0.75, bottom: 0 },
    })

    chartRef.current = chart
    seriesRef.current = series
    volumeRef.current = volume
    markerPrimitiveRef.current = createSeriesMarkers(series, [])

    const onCrosshairMove = (param: { time?: unknown }) => {
      if (typeof param.time !== 'number') {
        setHovered(null)
        return
      }
      const candle = orderedRef.current.find(
        item => Math.floor(new Date(item.timestamp).getTime() / 1000) === param.time,
      )
      setHovered(candle ?? null)
    }
    chart.subscribeCrosshairMove(onCrosshairMove)

    const onClick = (param: { time?: unknown }) => {
      if (typeof param.time !== 'number' || !onMarkerSelectRef.current) return
      const clicked = markersRef.current
        .filter(marker => Math.floor(new Date(marker.timestamp).getTime() / 1000) === param.time)
        .sort((left, right) => Number(Boolean(right.payload)) - Number(Boolean(left.payload)))[0]
      if (clicked) onMarkerSelectRef.current(clicked)
    }
    chart.subscribeClick(onClick)

    const ro = new ResizeObserver(entries => {
      for (const entry of entries) {
        const { width, height } = entry.contentRect
        chart.applyOptions({ width, height: Math.max(240, height) })
      }
    })
    ro.observe(el)

    return () => {
      chart.unsubscribeCrosshairMove(onCrosshairMove)
      chart.unsubscribeClick(onClick)
      ro.disconnect()
      chart.remove()
      chartRef.current = null
      seriesRef.current = null
      volumeRef.current = null
      markerPrimitiveRef.current = null
      priceLineRefs.current = []
    }
  }, [])

  useEffect(() => {
    const series = seriesRef.current
    const volume = volumeRef.current
    const chart = chartRef.current
    if (!series || !volume || !chart) return

    const data = orderedCandles
      .map(candle => ({
        time: Math.floor(new Date(candle.timestamp).getTime() / 1000) as UTCTimestamp,
        open: candle.open,
        high: candle.high,
        low: candle.low,
        close: candle.close,
      }))
      .sort((a, b) => a.time - b.time)
    const vol = orderedCandles
      .map(candle => ({
        time: Math.floor(new Date(candle.timestamp).getTime() / 1000) as UTCTimestamp,
        value: candle.tick_volume,
        color: candle.close >= candle.open ? 'rgba(16,185,129,0.45)' : 'rgba(239,68,68,0.45)',
      }))
      .sort((a, b) => a.time - b.time)

    series.setData(data)
    volume.setData(vol)

    if (data.length <= 1) {
      chart.timeScale().fitContent()
      return
    }
    const visibleCount = Math.max(1, Math.min(range, data.length))
    const to = data.length - 1
    const from = Math.max(0, to - visibleCount + 1)
    chart.timeScale().setVisibleLogicalRange({ from, to })
  }, [orderedCandles, range, resetNonce])

  useEffect(() => {
    const series = seriesRef.current
    if (!series) return

    for (const line of priceLineRefs.current) {
      series.removePriceLine(line)
    }
    priceLineRefs.current = priceLines
      .filter(line => Number.isFinite(line.price))
      .map(line =>
        series.createPriceLine({
          price: line.price,
          title: line.title,
          color: line.color,
          lineWidth: 1,
          axisLabelVisible: true,
          lineVisible: true,
          lineStyle: line.lineStyle ?? LineStyle.Dashed,
        }),
      )
  }, [priceLines])

  useEffect(() => {
    const markerPrimitive = markerPrimitiveRef.current
    if (!markerPrimitive) return

    const markerData: SeriesMarker<UTCTimestamp>[] = markers
      .map(marker => ({
        time: Math.floor(new Date(marker.timestamp).getTime() / 1000) as UTCTimestamp,
        position: marker.position,
        shape: marker.shape,
        color: marker.color,
        text: marker.text,
      }))
      .sort((a, b) => a.time - b.time)
    markerPrimitive.setMarkers(markerData)
  }, [markers])

  return (
    <div className="w-full h-full min-h-[260px] flex flex-col gap-2">
      <div className="flex items-center justify-between text-xs text-gray-400 gap-3">
        <div className="min-w-0 truncate flex items-center gap-2">
          <button
            onClick={() => {
              setRange(initialRange)
              setResetNonce(value => value + 1)
            }}
            className="px-2 py-0.5 rounded border border-gray-700 bg-gray-900 text-gray-300 hover:text-white shrink-0"
          >
            Reset
          </button>
          {hovered ? (
            <span>
              {hovered.timestamp} | O {hovered.open.toFixed(5)} H {hovered.high.toFixed(5)} L {hovered.low.toFixed(5)} C {hovered.close.toFixed(5)}
            </span>
          ) : (
            <span>Move mouse over a candle for OHLC.</span>
          )}
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {controls ? <div className="flex items-center gap-1">{controls}</div> : null}
          {ranges.map(n => (
            <button
              key={n}
              onClick={() => setRange(n)}
              className={[
                'px-2 py-0.5 rounded border text-xs',
                range === n
                  ? 'bg-emerald-800/40 border-emerald-500 text-emerald-300'
                  : 'bg-gray-900 border-gray-700 text-gray-400 hover:text-gray-200',
              ].join(' ')}
            >
              {n}
            </button>
          ))}
        </div>
      </div>
      <div className="flex-1 border border-gray-700 rounded overflow-hidden">
        <div ref={containerRef} className="w-full h-full" />
      </div>
    </div>
  )
})
