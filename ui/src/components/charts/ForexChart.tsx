import { forwardRef, useCallback, useEffect, useImperativeHandle, useMemo, useRef, useState, type ReactNode } from 'react'
import {
  CandlestickSeries,
  HistogramSeries,
  LineSeries,
  LineStyle,
  createChart,
  createSeriesMarkers,
  type IChartApi,
  type ISeriesApi,
  type SeriesMarker,
  type UTCTimestamp,
  type WhitespaceData,
} from 'lightweight-charts'

import type { CandleBar, IndicatorValue } from '@/api/client'
import type { Drawing, DrawingPoint, DrawingStyle, DrawingToolName } from './drawing/types'
import { DrawingManager } from './drawing/DrawingManager'
import { SessionBandsPrimitive, type SessionBandEntry } from './SessionBandsPrimitive'

export type { SessionBandEntry }

export interface ForexChartPriceLine {
  price: number
  title: string
  color: string
  lineStyle?: LineStyle
  lineWidth?: number
}

export interface ForexChartMarker {
  timestamp: string
  position: 'aboveBar' | 'belowBar' | 'inBar'
  shape: 'arrowUp' | 'arrowDown' | 'circle' | 'square'
  color: string
  text?: string
  payload?: unknown
}

export interface ForexChartOverlayLine {
  key: string
  label: string
  color: string
  lineWidth?: number
  lineStyle?: LineStyle
  values: IndicatorValue[]
}

export interface ForexChartOscillator {
  key: string
  label: string
  color: string
  lineWidth?: number
  lineStyle?: LineStyle
  precision?: number
  values: IndicatorValue[]
  zeroline?: boolean   // draw a dashed line at value=0
}

interface ForexChartProps {
  candles: CandleBar[]
  priceLines?: ForexChartPriceLine[]
  markers?: ForexChartMarker[]
  overlayLines?: ForexChartOverlayLine[]
  oscillators?: ForexChartOscillator[]
  ranges?: number[]
  initialRange?: number
  range?: number
  futureBars?: number
  controls?: ReactNode
  indicatorControls?: ReactNode
  sessionBands?: SessionBandEntry[]
  panMode?: boolean
  onRangeChange?: (range: number) => void
  onMarkerSelect?: (marker: ForexChartMarker) => void
  onCandleClick?: (candle: CandleBar) => void
  onDrawingComplete?: (drawing: Drawing) => void
  onPendingPoint?: (tool: DrawingToolName, points: DrawingPoint[]) => void
}

export interface ForexChartHandle {
  captureImage: () => string | null
  captureImageForPrint: () => string | null
  resetView: () => void
  startDrawing: (tool: DrawingToolName, style: DrawingStyle) => void
  cancelDrawing: () => void
  addDrawing: (drawing: Drawing) => void
  removeDrawing: (id: string) => void
  updateDrawing: (id: string, patch: Partial<Drawing>) => void
  getDrawings: () => Drawing[]
}

import { formatChartHM } from '@/utils/time'

export const ForexChart = forwardRef<ForexChartHandle, ForexChartProps>(function ForexChart({
  candles,
  priceLines = [],
  markers = [],
  overlayLines = [],
  oscillators = [],
  sessionBands,
  ranges = [20, 50, 100],
  initialRange = 100,
  range: controlledRange,
  futureBars = 0,
  controls = null,
  indicatorControls = null,
  panMode = false,
  onRangeChange,
  onMarkerSelect,
  onCandleClick,
  onDrawingComplete,
  onPendingPoint,
}: ForexChartProps, ref) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const seriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null)
  const volumeRef = useRef<ISeriesApi<'Histogram'> | null>(null)
  const markerPrimitiveRef = useRef<{ setMarkers: (markers: SeriesMarker<UTCTimestamp>[]) => void } | null>(null)
  const priceLineRefs = useRef<Array<ReturnType<ISeriesApi<'Candlestick'>['createPriceLine']>>>([])
  const overlaySeriesRef = useRef<Map<string, ISeriesApi<'Line'>>>(new Map())
  const oscillatorSeriesRef = useRef<Map<string, ISeriesApi<'Line'>>>(new Map())
  const orderedRef = useRef<CandleBar[]>([])
  const markersRef = useRef<ForexChartMarker[]>([])
  const onMarkerSelectRef = useRef<typeof onMarkerSelect>(onMarkerSelect)
  const onCandleClickRef = useRef<typeof onCandleClick>(onCandleClick)
  const onDrawingCompleteRef = useRef<typeof onDrawingComplete>(onDrawingComplete)
  const onPendingPointRef = useRef<typeof onPendingPoint>(onPendingPoint)
  const drawingManagerRef = useRef<DrawingManager | null>(null)
  const sessionBandsPrimitiveRef = useRef<SessionBandsPrimitive | null>(null)
  const panModeRef = useRef(panMode)
  const pendingToolRef = useRef<DrawingToolName | null>(null)
  const pendingStyleRef = useRef<DrawingStyle | null>(null)
  const pendingPointsRef = useRef<Array<{ price: number; time: UTCTimestamp }>>([])
  const [range, setRange] = useState(controlledRange ?? initialRange)
  useEffect(() => { if (controlledRange !== undefined) setRange(controlledRange) }, [controlledRange])
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

  useEffect(() => {
    onPendingPointRef.current = onPendingPoint
  }, [onPendingPoint])

  useEffect(() => {
    onCandleClickRef.current = onCandleClick
  }, [onCandleClick])

  useEffect(() => {
    onDrawingCompleteRef.current = onDrawingComplete
  }, [onDrawingComplete])

  useEffect(() => {
    panModeRef.current = panMode
    const chart = chartRef.current
    if (!chart) return
    if (panMode) {
      // Pan mode: disable all lwc native drag so our handlers have full control
      chart.applyOptions({
        handleScroll: { mouseWheel: false, pressedMouseMove: false, horzTouchDrag: false, vertTouchDrag: false },
        handleScale: { mouseWheel: true, pinch: false, axisPressedMouseMove: { time: false, price: false } },
      })
    } else {
      // Zoom/default mode: restore lwc native scroll+scale
      chart.applyOptions({
        handleScroll: { mouseWheel: false, pressedMouseMove: true, horzTouchDrag: true, vertTouchDrag: false },
        handleScale: { mouseWheel: true, pinch: true, axisPressedMouseMove: { time: true, price: true } },
      })
      // Re-enable auto-scale when leaving pan mode
      chart.priceScale('right').applyOptions({ autoScale: true, scaleMargins: { top: 0.08, bottom: 0.32 } })
    }
  }, [panMode])

  useImperativeHandle(ref, () => ({
    captureImage: () => {
      const chart = chartRef.current as (IChartApi & { takeScreenshot?: (addTopLayer?: boolean, includeCrosshair?: boolean) => HTMLCanvasElement }) | null
      const screenshot = chart?.takeScreenshot?.(true, true)
      return screenshot ? screenshot.toDataURL('image/png') : null
    },
    captureImageForPrint: () => {
      // Switch to light theme, capture, then restore dark theme
      const chart = chartRef.current as (IChartApi & { takeScreenshot?: (addTopLayer?: boolean, includeCrosshair?: boolean) => HTMLCanvasElement }) | null
      if (!chart) return null
      // Apply light theme
      chart.applyOptions({
        layout: { background: { color: '#ffffff' }, textColor: '#111827' },
        grid: { vertLines: { color: '#e5e7eb' }, horzLines: { color: '#e5e7eb' } },
      })
      const screenshot = chart.takeScreenshot?.(true, false)
      // Restore dark theme
      chart.applyOptions({
        layout: { background: { color: '#111827' }, textColor: '#9ca3af' },
        grid: { vertLines: { color: '#1f2937' }, horzLines: { color: '#1f2937' } },
      })
      return screenshot ? screenshot.toDataURL('image/png') : null
    },
    resetView: () => {
      setRange(initialRange)
      setResetNonce(value => value + 1)
    },
    startDrawing: (tool: DrawingToolName, style: DrawingStyle) => {
      pendingToolRef.current = tool
      pendingStyleRef.current = style
      pendingPointsRef.current = []
    },
    cancelDrawing: () => {
      pendingToolRef.current = null
      pendingStyleRef.current = null
      pendingPointsRef.current = []
    },
    addDrawing: (drawing: Drawing) => {
      drawingManagerRef.current?.add(drawing)
    },
    removeDrawing: (id: string) => {
      drawingManagerRef.current?.remove(id)
    },
    updateDrawing: (id: string, patch: Partial<Drawing>) => {
      drawingManagerRef.current?.update(id, patch)
    },
    getDrawings: () => drawingManagerRef.current?.getAll() ?? [],
  }), [])

  useEffect(() => {
    const el = containerRef.current
    if (!el) return

    const chart = createChart(el, {
      width: el.clientWidth,
      height: el.clientHeight || 320,
      layout: {
        background: { color: '#ffffff' },
        textColor: '#111827',
      },
      localization: {
        timeFormatter: (time: unknown) => formatChartHM(Number(time)),
      },
      grid: {
        vertLines: { color: '#e5e7eb' },
        horzLines: { color: '#e5e7eb' },
      },
      handleScroll: {
        mouseWheel: false,       // wheel zooms X (handleScale.mouseWheel), not scrolls
        pressedMouseMove: true,  // drag pans X
        horzTouchDrag: true,
        vertTouchDrag: false,    // vertical touch handled by custom pan
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
        tickMarkFormatter: (time: unknown) => formatChartHM(Number(time)),
      },
      rightPriceScale: {
        borderColor: '#374151',
      },
      crosshair: {
        vertLine: { color: '#000000' },
        horzLine: { color: '#000000' },
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
    drawingManagerRef.current = new DrawingManager(series, chart)

    const sessionBandsPrimitive = new SessionBandsPrimitive()
    series.attachPrimitive(sessionBandsPrimitive)
    sessionBandsPrimitiveRef.current = sessionBandsPrimitive

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

    const onClick = (param: { time?: unknown; point?: { x: number; y: number } }) => {
      if (typeof param.time !== 'number') return

      // Drawing mode: collect point and potentially finalize the drawing
      if (pendingToolRef.current && param.point) {
        const price = seriesRef.current?.coordinateToPrice(param.point.y) ?? null
        if (price !== null) {
          const pt = { price, time: param.time as UTCTimestamp }
          pendingPointsRef.current = [...pendingPointsRef.current, pt]
          const requiredPoints: Record<DrawingToolName, number | null> = {
            hline: 1, vline: 1, ray: 1, extended_line: 2, trendline: 2, channel: 3,
            rect: 2, textlabel: 1, arrow_up: 1, arrow_down: 1,
            fib_ret: 2, fib_ext: 3, fib_fan: 2, fib_timezones: 2,
            pitchfork: 3, elliott: null, measure: 2,
          }
          const needed = requiredPoints[pendingToolRef.current]
          if (needed === null) {
            // Variable-point tool (e.g. Elliott): notify parent of each new point
            onPendingPointRef.current?.(pendingToolRef.current, [...pendingPointsRef.current])
          } else if (pendingPointsRef.current.length >= needed) {
            const drawing: Drawing = {
              id: `drawing_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`,
              tool: pendingToolRef.current,
              points: pendingPointsRef.current.slice(0, needed),
              style: pendingStyleRef.current ?? { color: '#f59e0b', lineStyle: 0, lineWidth: 1 },
              visible: true,
              selected: false,
            }
            drawingManagerRef.current?.add(drawing)
            pendingPointsRef.current = []
            pendingToolRef.current = null
            pendingStyleRef.current = null
            onDrawingCompleteRef.current?.(drawing)
          }
          return
        }
      }

      // Marker click
      const markerClicked = markersRef.current
        .filter(marker => Math.floor(new Date(marker.timestamp).getTime() / 1000) === param.time)
        .sort((left, right) => Number(Boolean(right.payload)) - Number(Boolean(left.payload)))[0]
      if (markerClicked) {
        onMarkerSelectRef.current?.(markerClicked)
        return
      }

      // Candle click
      const candle = orderedRef.current.find(
        c => Math.floor(new Date(c.timestamp).getTime() / 1000) === param.time,
      )
      if (candle) onCandleClickRef.current?.(candle)
    }
    chart.subscribeClick(onClick)

    const ro = new ResizeObserver(entries => {
      for (const entry of entries) {
        const { width, height } = entry.contentRect
        chart.applyOptions({ width, height: Math.max(240, height) })
      }
    })
    ro.observe(el)

    // ── Pan mode: full X+Y drag (only active when panModeRef.current === true) ─
    // In pan mode, lwc native pressedMouseMove is disabled so we handle X+Y ourselves.
    // Y: adjust scaleMargins symmetrically → no zoom change, only position shift.
    // X: shift visibleLogicalRange by dx bars.
    const pan = {
      active: false,
      startX: 0, startY: 0,
      startTop: 0.08, startBottom: 0.32,
      paneWidth: 800, paneHeight: 400,
      logicalFrom: 0, logicalTo: 200,
      logicalPerPx: 0.25,
    }

    function onPanMouseDown(e: MouseEvent) {
      if (e.button !== 0 || !panModeRef.current) return
      const rect = el!.getBoundingClientRect()
      const sm = chart.priceScale('right').options().scaleMargins ?? { top: 0.08, bottom: 0.32 }
      const lr = chart.timeScale().getVisibleLogicalRange()
      pan.active = true
      pan.startX = e.clientX
      pan.startY = e.clientY
      pan.paneWidth = Math.max(rect.width, 1)
      pan.paneHeight = Math.max(rect.height, 1)
      pan.startTop = sm.top
      pan.startBottom = sm.bottom
      pan.logicalFrom = lr?.from ?? 0
      pan.logicalTo = lr?.to ?? 200
      pan.logicalPerPx = lr ? (lr.to - lr.from) / pan.paneWidth : 0.25
      chart.priceScale('right').applyOptions({ autoScale: false })
      e.preventDefault()
    }

    function onPanMouseMove(e: MouseEvent) {
      if (!pan.active || e.buttons !== 1) { pan.active = false; return }
      if (!panModeRef.current) { pan.active = false; return }

      // X pan: shift logical range
      const dx = e.clientX - pan.startX
      const logicalShift = -dx * pan.logicalPerPx
      chart.timeScale().setVisibleLogicalRange({
        from: pan.logicalFrom + logicalShift,
        to: pan.logicalTo + logicalShift,
      })

      // Y pan: adjust scaleMargins symmetrically (no zoom change)
      const dy = e.clientY - pan.startY
      const rawDelta = -dy / pan.paneHeight
      const maxDelta = Math.min(pan.startTop - 0.01, 0.95 - pan.startBottom)
      const minDelta = Math.max(pan.startTop - 0.95, 0.01 - pan.startBottom)
      const delta = Math.max(minDelta, Math.min(maxDelta, rawDelta))
      chart.priceScale('right').applyOptions({
        scaleMargins: { top: pan.startTop - delta, bottom: pan.startBottom + delta },
      })
    }

    function onPanMouseUp() { pan.active = false }

    // Double-click resets to auto-scale (works in both modes)
    function onPanDblClick() {
      chart.priceScale('right').applyOptions({ autoScale: true, scaleMargins: { top: 0.08, bottom: 0.32 } })
    }

    el.addEventListener('mousedown', onPanMouseDown)
    el.addEventListener('mousemove', onPanMouseMove)
    el.addEventListener('mouseup', onPanMouseUp)
    el.addEventListener('dblclick', onPanDblClick)

    return () => {
      el.removeEventListener('mousedown', onPanMouseDown)
      el.removeEventListener('mousemove', onPanMouseMove)
      el.removeEventListener('mouseup', onPanMouseUp)
      el.removeEventListener('dblclick', onPanDblClick)
      chart.unsubscribeCrosshairMove(onCrosshairMove)
      chart.unsubscribeClick(onClick)
      ro.disconnect()
      drawingManagerRef.current?.clear()
      drawingManagerRef.current = null
      sessionBandsPrimitiveRef.current = null
      chart.remove()
      chartRef.current = null
      seriesRef.current = null
      volumeRef.current = null
      markerPrimitiveRef.current = null
      priceLineRefs.current = []
      overlaySeriesRef.current.clear()
      oscillatorSeriesRef.current.clear()
    }
  }, [])

  const futureBarsRef   = useRef(futureBars)
  futureBarsRef.current = futureBars
  const initialLoadDone = useRef(false)

  const applyVisibleRange = useCallback(() => {
    const chart = chartRef.current
    if (!chart) return
    const data = orderedRef.current
    if (data.length <= 1) return
    const pad = Math.max(futureBarsRef.current, 6)
    const realBars = data.length
    const visibleCount = Math.max(1, Math.min(range, realBars))
    const lastReal = realBars - 1
    const from = Math.max(0, lastReal - visibleCount + 1)
    chart.timeScale().setVisibleLogicalRange({ from, to: lastReal + pad })
  }, [range])

  useEffect(() => {
    const series = seriesRef.current
    const volume = volumeRef.current
    if (!series || !volume) return

    const data = orderedCandles
      .map(c => ({
        time: Math.floor(new Date(c.timestamp).getTime() / 1000) as UTCTimestamp,
        open: c.open, high: c.high, low: c.low, close: c.close,
      }))
      .sort((a, b) => a.time - b.time)
    const vol = orderedCandles
      .map(c => ({
        time:  Math.floor(new Date(c.timestamp).getTime() / 1000) as UTCTimestamp,
        value: c.tick_volume,
        color: c.close >= c.open ? 'rgba(16,185,129,0.45)' : 'rgba(239,68,68,0.45)',
      }))
      .sort((a, b) => a.time - b.time)

    const barInterval = data.length > 1 ? data[1].time - data[0].time : 300
    const lastTime    = data.length > 0 ? data[data.length - 1].time : 0
    const whitespace: WhitespaceData[] = Array.from({ length: 200 }, (_, i) => ({
      time: (lastTime + (i + 1) * barInterval) as UTCTimestamp,
    }))

    series.setData([...data, ...whitespace])
    volume.setData(vol)

    if (!initialLoadDone.current) {
      initialLoadDone.current = true
      if (data.length <= 1) {
        chartRef.current?.timeScale().fitContent()
      } else {
        applyVisibleRange()
      }
    }
    // On subsequent 30s refreshes setData() replaces data silently — zoom preserved
  }, [orderedCandles])   // NO applyVisibleRange in deps — prevents zoom reset on every candle update

  useEffect(() => {
    if (initialLoadDone.current) applyVisibleRange()
  }, [applyVisibleRange, resetNonce])

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
          lineWidth: (line.lineWidth ?? 1) as 1 | 2 | 3 | 4,
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

  useEffect(() => {
    const primitive = sessionBandsPrimitiveRef.current
    if (!primitive) return
    primitive.updateBands(sessionBands ?? [])
    // Nudge the series to trigger a repaint so band changes appear immediately
    seriesRef.current?.applyOptions({ visible: true })
  }, [sessionBands])

  useEffect(() => {
    const chart = chartRef.current
    if (!chart) return

    const lastRef = orderedRef.current
    const firstCandleTime = lastRef.length > 0
      ? Math.floor(new Date(lastRef[0].timestamp).getTime() / 1000)
      : 0
    const lastCandleTime = lastRef.length > 0
      ? Math.floor(new Date(lastRef[lastRef.length - 1].timestamp).getTime() / 1000)
      : Infinity

    for (const [key, series] of overlaySeriesRef.current) {
      if (!overlayLines.find(l => l.key === key)) {
        chart.removeSeries(series)
        overlaySeriesRef.current.delete(key)
      }
    }
    for (const line of overlayLines) {
      if (!overlaySeriesRef.current.has(line.key)) {
        const s = chart.addSeries(LineSeries, {
          color: line.color,
          lineWidth: (line.lineWidth ?? 1) as 1 | 2 | 3 | 4,
          lineStyle: line.lineStyle ?? LineStyle.Solid,
          priceScaleId: 'right',
          crosshairMarkerVisible: false,
          lastValueVisible: true,
          priceLineVisible: false,
        })
        overlaySeriesRef.current.set(line.key, s)
      }
      const s = overlaySeriesRef.current.get(line.key)!
      s.applyOptions({ color: line.color, lineWidth: (line.lineWidth ?? 1) as 1 | 2 | 3 | 4, lineStyle: line.lineStyle ?? LineStyle.Solid })
      const raw = (line.values ?? [])
        .map(v => ({ time: Math.floor(new Date(v.timestamp).getTime() / 1000) as UTCTimestamp, value: v.value }))
        .sort((a, b) => a.time - b.time)
      const filtered = raw.filter(v => v.time >= firstCandleTime && v.time <= lastCandleTime)
      const outside = raw.filter(v => v.time < firstCandleTime || v.time > lastCandleTime)
      void fetch('/debug/log', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message:
          `[overlay:${line.key}] total=${raw.length} in-range=${filtered.length} outside=${outside.length}` +
          ` | chart: ${new Date(firstCandleTime * 1000).toISOString()} → ${new Date(lastCandleTime * 1000).toISOString()}` +
          (outside.length > 0 ? ` | outside-range: ${outside.map(v => new Date(v.time * 1000).toISOString()).join(', ')}` : ' | no outside'),
        }),
      })
      s.setData(filtered)
    }
  }, [overlayLines])

  useEffect(() => {
    const chart = chartRef.current
    if (!chart) return

    const lastRef = orderedRef.current
    const firstCandleTime = lastRef.length > 0
      ? Math.floor(new Date(lastRef[0].timestamp).getTime() / 1000)
      : 0
    const lastCandleTime = lastRef.length > 0
      ? Math.floor(new Date(lastRef[lastRef.length - 1].timestamp).getTime() / 1000)
      : Infinity

    for (const [key, series] of oscillatorSeriesRef.current) {
      if (!oscillators.find(o => o.key === key)) {
        chart.removeSeries(series)
        oscillatorSeriesRef.current.delete(key)
      }
    }
    for (const osc of oscillators) {
      if (!oscillatorSeriesRef.current.has(osc.key)) {
        const precision = osc.precision ?? 2
        const s = chart.addSeries(LineSeries, {
          color: osc.color,
          lineWidth: (osc.lineWidth ?? 1) as 1 | 2 | 3 | 4,
          lineStyle: osc.lineStyle ?? LineStyle.Solid,
          priceScaleId: osc.key,
          crosshairMarkerVisible: false,
          lastValueVisible: true,
          priceLineVisible: false,
          priceFormat: { type: 'price', precision, minMove: Math.pow(10, -precision) },
        })
        // Add zero line for slope indicators
        if (osc.zeroline) {
          s.createPriceLine({
            price: 0,
            color: '#6b7280',
            lineWidth: 1,
            lineStyle: LineStyle.Dashed,
            axisLabelVisible: true,
            title: '0',
          })
        }
        oscillatorSeriesRef.current.set(osc.key, s)
      }
      oscillatorSeriesRef.current.get(osc.key)!.applyOptions({ color: osc.color, lineWidth: (osc.lineWidth ?? 1) as 1 | 2 | 3 | 4, lineStyle: osc.lineStyle ?? LineStyle.Solid })
      oscillatorSeriesRef.current.get(osc.key)!.setData(
        (osc.values ?? [])
          .map(v => ({ time: Math.floor(new Date(v.timestamp).getTime() / 1000) as UTCTimestamp, value: v.value }))
          .filter(v => v.time >= firstCandleTime && v.time <= lastCandleTime)
          .sort((a, b) => a.time - b.time),
      )
    }

    const N = oscillators.length
    // Each oscillator gets 15% of chart height, capped so main chart keeps at least 35%
    const oscH   = 0.15
    const volH   = 0.10
    const bottom = Math.min(0.55, N * oscH + volH)
    chart.priceScale('right').applyOptions({ scaleMargins: { top: 0.05, bottom: bottom } })
    chart.priceScale('volume').applyOptions({
      scaleMargins: { top: 1 - volH - N * oscH, bottom: N * oscH },
    })
    for (let i = 0; i < N; i++) {
      const j = N - 1 - i
      chart.priceScale(oscillators[i].key).applyOptions({
        scaleMargins: { top: 1 - (j + 1) * oscH, bottom: j * oscH },
      })
    }
  }, [oscillators])

  return (
    <div className="w-full h-full min-h-[260px] flex flex-col gap-2">
      <div className="flex items-center justify-between text-xs text-gray-400 gap-3">
        <div className="min-w-0 truncate flex items-center gap-2">
          {hovered ? (
            <span>
              {(() => {
                const pipSize = hovered.close > 20 ? 0.01 : 0.0001
                const oc = Math.abs(hovered.close - hovered.open) / pipSize
                const hl = (hovered.high - hovered.low) / pipSize
                return (
                  <>
                    {hovered.timestamp} | O {hovered.open.toFixed(5)} H {hovered.high.toFixed(5)} L {hovered.low.toFixed(5)} C {hovered.close.toFixed(5)}
                    <span className="text-gray-400"> | OC {oc.toFixed(1)}p HL {hl.toFixed(1)}p</span>
                  </>
                )
              })()}
              {overlayLines.map(line => {
                const ts = Math.floor(new Date(hovered.timestamp).getTime() / 1000)
                const val = line.values.find(v => Math.floor(new Date(v.timestamp).getTime() / 1000) === ts)
                return val != null
                  ? <span key={line.key} style={{ color: line.color }}> | {line.label} {val.value.toFixed(5)}</span>
                  : null
              })}
              {oscillators.map(osc => {
                const ts = Math.floor(new Date(hovered.timestamp).getTime() / 1000)
                const val = osc.values.find(v => Math.floor(new Date(v.timestamp).getTime() / 1000) === ts)
                return val != null
                  ? <span key={osc.key} style={{ color: osc.color }}> | {osc.label} {val.value.toFixed(osc.precision ?? 2)}</span>
                  : null
              })}
            </span>
          ) : null}
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {controls ? <div className="flex items-center gap-1">{controls}</div> : null}
          {ranges.map(n => (
            <button
              key={n}
              onClick={() => { setRange(n); onRangeChange?.(n) }}
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
      {indicatorControls && (
        <div className="flex items-center flex-wrap gap-x-4 gap-y-1 text-xs text-gray-400">
          {indicatorControls}
        </div>
      )}
      <div className="flex-1 border border-gray-700 rounded overflow-hidden">
        <div ref={containerRef} className="w-full h-full" />
      </div>
    </div>
  )
})
