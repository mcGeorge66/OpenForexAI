import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { BookOpen, Check, Copy, Eye, EyeOff, Plus, Printer, RefreshCcw, Trash2, Undo2 } from 'lucide-react'
import { LineStyle, type UTCTimestamp } from 'lightweight-charts'

import { api, type AnalysisRecord, type CandleBar, type IndicatorValue, type InitialConsoleModuleItem } from '@/api/client'
import { kbImport } from '@/knowledgebase/kbImport'
import {
  ForexChart,
  type ForexChartHandle,
  type ForexChartMarker,
  type ForexChartOscillator,
  type ForexChartOverlayLine,
  type ForexChartPriceLine,
  type SessionBandEntry,
} from '@/components/charts/ForexChart'
import { TF_MINUTES } from '@/utils/indicators'
import type { Drawing, DrawingStyle, DrawingToolName } from '@/components/charts/drawing/types'
import { REQUIRED_POINTS, TOOL_LABELS } from '@/components/charts/drawing/types'

// ── Helpers ───────────────────────────────────────────────────────────────────

function uid(): string {
  return `d_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`
}

function CopyButton({ getText }: { getText: () => string }) {
  const [copied, setCopied] = useState(false)
  return (
    <button
      type="button"
      title="Copy to clipboard"
      onClick={() => {
        void navigator.clipboard.writeText(getText()).then(() => {
          setCopied(true)
          setTimeout(() => setCopied(false), 1500)
        })
      }}
      className="inline-flex items-center text-gray-500 hover:text-gray-300 transition-colors"
    >
      {copied ? <Check className="w-3 h-3 text-emerald-400" /> : <Copy className="w-3 h-3" />}
    </button>
  )
}

const TIMEFRAMES = Object.keys(TF_MINUTES).filter(tf => tf !== 'M1')

const INDICATOR_DEFS: Array<{ name: IndicatorName; label: string; isOscillator: boolean; defaultPeriod: number; hasBackend: boolean }> = [
  { name: 'EMA',       label: 'EMA',       isOscillator: false, defaultPeriod: 20, hasBackend: false },
  { name: 'SMA',       label: 'SMA',       isOscillator: false, defaultPeriod: 20, hasBackend: false },
  { name: 'RSI',       label: 'RSI',       isOscillator: true,  defaultPeriod: 14, hasBackend: false },
  { name: 'ATR',       label: 'ATR',       isOscillator: true,  defaultPeriod: 14, hasBackend: true  },
  { name: 'BB',        label: 'BB',        isOscillator: false, defaultPeriod: 20, hasBackend: true  },
  { name: 'VWAP',      label: 'VWAP',      isOscillator: false, defaultPeriod: 0,  hasBackend: true  },
  { name: 'SLOPE_E', label: 'SlopeE', isOscillator: true,  defaultPeriod: 20, hasBackend: true  },
  { name: 'SLOPE_S', label: 'SlopeS', isOscillator: true,  defaultPeriod: 20, hasBackend: true  },
]

const LINE_STYLE_OPTIONS: Array<{ value: LineStyle; label: string }> = [
  { value: LineStyle.Solid,       label: 'Solid'       },
  { value: LineStyle.Dashed,      label: 'Dashed'      },
  { value: LineStyle.LargeDashed, label: 'LargeDashed' },
  { value: LineStyle.Dotted,      label: 'Dotted'      },
  { value: LineStyle.SparseDotted,label: 'SparseDotted'},
]

type IndicatorName = 'EMA' | 'SMA' | 'RSI' | 'ATR' | 'BB' | 'VWAP' | 'SLOPE_E' | 'SLOPE_S'

type DXYEntry = { dxy_close: number; dxy_direction: string; correlation: number }

interface IndicatorInstance {
  id: string
  name: IndicatorName
  period: number
  timeframe: string
  color: string
  lineStyle: LineStyle
  lineWidth: number
  visible: boolean
  data: IndicatorValue[]
  bbData?: { upper: IndicatorValue[]; middle: IndicatorValue[]; lower: IndicatorValue[] }
  smoothPeriod?: number   // EMA smoothing applied to output (for slope indicators)
}

const DEFAULT_COLORS = ['#10b981', '#3b82f6', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899', '#06b6d4', '#84cc16']

// Drawing tool categories for the toolbar
const TOOL_GROUPS: Array<{ label: string; tools: DrawingToolName[] }> = [
  { label: 'Lines',             tools: ['hline', 'vline', 'ray', 'extended_line', 'trendline', 'channel'] },
  { label: 'Fibonacci',         tools: ['fib_ret', 'fib_ext', 'fib_fan', 'fib_timezones'] },
  { label: 'Marker',            tools: ['arrow_up', 'arrow_down', 'rect', 'textlabel', 'measure'] },
  { label: 'Advanced',          tools: ['pitchfork', 'elliott'] },
]

const DEFAULT_DRAWING_STYLE: DrawingStyle = {
  color: '#f59e0b',
  lineStyle: LineStyle.Solid,
  lineWidth: 1,
  fillColor: '#f59e0b',
  fillOpacity: 0.15,
}

// ── Session bands ─────────────────────────────────────────────────────────────

// Sessions defined by their local open/close hours (same 08:00-17:00 local for all).
// DST is handled automatically by Intl.DateTimeFormat.
const _SESSION_DEFS = [
  // Local open/close hours in the session's home timezone.
  // UTC equivalents (approx): SYD 22:00–07:00 | TKY 00:00–09:00 | LON 08:00–17:00 | NYC 13:00–22:00
  { label: 'SYD', tz: 'Australia/Sydney',  openHour:  8, closeHour: 17, color: 'rgb(59,130,246)'  },
  { label: 'TKY', tz: 'Asia/Tokyo',        openHour:  9, closeHour: 18, color: 'rgb(245,158,11)'  },
  { label: 'LON', tz: 'Europe/London',     openHour:  8, closeHour: 17, color: 'rgb(16,185,129)'  },
  { label: 'NYC', tz: 'America/New_York',  openHour:  8, closeHour: 17, color: 'rgb(249,115,22)'  },
]

function computeSessionBands(candles: CandleBar[]): SessionBandEntry[] {
  if (candles.length === 0) return []

  // Candle timestamps now carry their proper timezone (+03:00 for broker
  // candles, UTC for OANDA, etc.). new Date() parses them to real UTC ms, so
  // no manual offset adjustment is needed before computing session windows.
  const bars = candles
    .map(c => ({
      brokerTs: Math.floor(new Date(c.timestamp).getTime() / 1000),
      utcMs:    new Date(c.timestamp).getTime(),
    }))
    .sort((a, b) => a.brokerTs - b.brokerTs)

  const totalRows = _SESSION_DEFS.length

  // One bar interval in seconds — used to extend endTs so the last candle body
  // is fully covered (candle timestamps mark the bar open, not close).
  const barInterval = bars.length > 1 ? bars[1].brokerTs - bars[0].brokerTs : 300

  // Per-session state: start/end broker-ts of the current open band.
  const openStart: (number | null)[] = new Array(totalRows).fill(null)
  const openEnd:   number[]          = new Array(totalRows).fill(0)
  const result: SessionBandEntry[] = []

  const flush = (i: number) => {
    if (openStart[i] === null) return
    result.push({
      startTs:  openStart[i]!,
      endTs:    openEnd[i] + barInterval,   // extend to cover the full last candle
      color:    _SESSION_DEFS[i].color,
      label:    _SESSION_DEFS[i].label,
      row:      i,
      totalRows,
    })
    openStart[i] = null
  }

  const fmt = _SESSION_DEFS.map(s =>
    new Intl.DateTimeFormat('en-GB', { timeZone: s.tz, hour: '2-digit', hour12: false })
  )

  for (const { brokerTs, utcMs } of bars) {
    const date = new Date(utcMs)
    for (let i = 0; i < totalRows; i++) {
      const h = parseInt(fmt[i].format(date), 10) % 24
      const active = h >= _SESSION_DEFS[i].openHour && h < _SESSION_DEFS[i].closeHour
      if (active) {
        if (openStart[i] === null) openStart[i] = brokerTs
        openEnd[i] = brokerTs
      } else {
        flush(i)
      }
    }
  }
  // Flush any session still active at the end of the loaded data
  for (let i = 0; i < totalRows; i++) flush(i)

  return result
}

function computeFutureBars(timeframe: string): number {
  const barMinutes = TF_MINUTES[timeframe] ?? 5
  const MIN_BARS = Math.ceil(60 / barMinutes) // always show at least 60 minutes
  const now = new Date()
  let maxBars = MIN_BARS

  for (const session of _SESSION_DEFS) {
    try {
      const fmtH = new Intl.DateTimeFormat('en-GB', { timeZone: session.tz, hour: '2-digit', hour12: false })
      const fmtM = new Intl.DateTimeFormat('en-GB', { timeZone: session.tz, minute: '2-digit', hour12: false })
      const hour   = parseInt(fmtH.format(now), 10) % 24
      const minute = parseInt(fmtM.format(now), 10)
      if (hour < session.openHour || hour >= session.closeHour) continue
      const minutesToClose = (session.closeHour - hour) * 60 - minute
      maxBars = Math.max(maxBars, Math.ceil(minutesToClose / barMinutes))
    } catch { /* ignore */ }
  }
  return maxBars
}

// ── Main Component ────────────────────────────────────────────────────────────

export function ChartAnalysis() {
  // Controls
  const [pair, setPair] = useState('')
  const [timeframe, setTimeframe] = useState('M5')
  const [candleCount, setCandleCount] = useState(200)

  // Broker
  const [brokerName, setBrokerName] = useState<string | null>(null)
  const [brokers, setBrokers] = useState<InitialConsoleModuleItem[]>([])

  // Data
  const [candles, setCandles] = useState<CandleBar[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [systemConfig, setSystemConfig] = useState<Record<string, unknown> | null>(null)

  // Indicators
  const [indicators, setIndicators] = useState<IndicatorInstance[]>([])
  // Ref so loadData always sees the current indicators without being in its dep array
  const indicatorsRef = useRef<IndicatorInstance[]>([])
  useEffect(() => { indicatorsRef.current = indicators }, [indicators])
  const recomputeTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Candle click
  const [selectedCandle, setSelectedCandle] = useState<CandleBar | null>(null)
  const [dxyData, setDxyData] = useState<Record<number, DXYEntry>>({})

  // Analyst view
  const [showAnalyses, setShowAnalyses] = useState(false)
  const [analysisRecords, setAnalysisRecords] = useState<AnalysisRecord[]>([])
  const [selectedAnalysis, setSelectedAnalysis] = useState<AnalysisRecord | null>(null)
  const [showAnalysisModal, setShowAnalysisModal] = useState(false)

  // Swing levels
  const [swingEnabled, setSwingEnabled] = useState(false)
  const [swingTf, setSwingTf] = useState('H1')
  const [swingCount, setSwingCount] = useState(5)
  const [swingAtrPeriod, setSwingAtrPeriod] = useState(14)
  const [swingMinGapAtr, setSwingMinGapAtr] = useState(0.3)
  const [swingLineWidth, setSwingLineWidth] = useState(2)
  const [swingLineStyle, setSwingLineStyle] = useState<LineStyle>(LineStyle.Dashed)
  const [swingPriceSource, setSwingPriceSource] = useState<'HL' | 'OC'>('HL')
  const [swingVisibleOnly, setSwingVisibleOnly] = useState(false)
  const [swingSortBy, setSwingSortBy] = useState<'nearest' | 'prominent'>('nearest')
  const swingSortByRef = useRef<'nearest' | 'prominent'>('nearest')
  useEffect(() => { swingSortByRef.current = swingSortBy }, [swingSortBy])
  const [visibleCandleCount, setVisibleCandleCount] = useState(candleCount)
  const [swingLines, setSwingLines] = useState<ForexChartPriceLine[]>([])
  const [swingLoading, setSwingLoading] = useState(false)

  // Session bands
  const [showSessionBands, setShowSessionBands] = useState(false)

  // Pan / zoom toggle
  const [panMode, setPanMode] = useState(false)

  // Drawing tools
  const [activeTool, setActiveTool] = useState<DrawingToolName | null>(null)
  const activeToolRef = useRef<DrawingToolName | null>(null)
  useEffect(() => { activeToolRef.current = activeTool }, [activeTool])
  const [multiUse, setMultiUse] = useState(false)
  const multiUseRef = useRef(false)
  useEffect(() => { multiUseRef.current = multiUse }, [multiUse])
  const [activeDrawingStyle, setActiveDrawingStyle] = useState<DrawingStyle>(DEFAULT_DRAWING_STYLE)
  const activeDrawingStyleRef = useRef<DrawingStyle>(DEFAULT_DRAWING_STYLE)
  useEffect(() => { activeDrawingStyleRef.current = activeDrawingStyle }, [activeDrawingStyle])
  const [drawings, setDrawings] = useState<Drawing[]>([])
  const [pendingClickCount, setPendingClickCount] = useState(0)

  // Elliott wave config
  const [elliottCount, setElliottCount] = useState(5)
  const [elliottMode, setElliottMode] = useState<'impulse' | 'corrective'>('impulse')
  const pendingElliottPointsRef = useRef<Array<{ price: number; time: number }>>([])

  // Print
  const [showPrintDialog, setShowPrintDialog] = useState(false)
  const [printOpts, setPrintOpts] = useState({ chart: true, candle: true, analysis: true })

  // KB import
  const [kbMsg, setKbMsg] = useState<string | null>(null)

  const chartRef = useRef<ForexChartHandle | null>(null)

  // ── Resizable bottom panel ─────────────────────────────────────────────────
  const [bottomHeight, setBottomHeight] = useState(300)
  const resizingRef = useRef(false)
  const resizeStartYRef = useRef(0)
  const resizeStartHeightRef = useRef(0)

  useEffect(() => {
    function onMouseMove(e: MouseEvent) {
      if (!resizingRef.current) return
      const delta = resizeStartYRef.current - e.clientY
      setBottomHeight(Math.max(120, Math.min(600, resizeStartHeightRef.current + delta)))
    }
    function onMouseUp() { resizingRef.current = false }
    document.addEventListener('mousemove', onMouseMove)
    document.addEventListener('mouseup', onMouseUp)
    return () => {
      document.removeEventListener('mousemove', onMouseMove)
      document.removeEventListener('mouseup', onMouseUp)
    }
  }, [])

  // ── Pair list ──────────────────────────────────────────────────────────────

  const availablePairs = useMemo(() => {
    const agentsCfg = (systemConfig?.agents ?? {}) as Record<string, Record<string, unknown>>
    const pairs = new Set<string>()
    for (const cfg of Object.values(agentsCfg)) {
      if (cfg.type === 'AA' && cfg.pair) pairs.add(String(cfg.pair).toUpperCase())
    }
    return [...pairs].sort()
  }, [systemConfig])

  useEffect(() => {
    void api.getSystemConfig().then(cfg => setSystemConfig(cfg)).catch(() => setSystemConfig(null))
  }, [])

  useEffect(() => {
    void api.getInitialConsole().then(res => {
      const connected = res.broker.items.filter(b => b.status === 'connected')
      setBrokers(connected)
      if (connected.length > 0) setBrokerName(b => b ?? connected[0].name)
    }).catch(() => {})
  }, [])

  useEffect(() => {
    if (!pair && availablePairs.length > 0) setPair(availablePairs[0])
  }, [availablePairs, pair])

  // ── Indicator computation ──────────────────────────────────────────────────

  const recomputeIndicators = useCallback(async (newCandles: CandleBar[], inds: IndicatorInstance[]) => {
    if (newCandles.length === 0) return inds

    const results = await Promise.all(inds.map(async ind => {
      if (!ind.visible) return ind

      try {
        const result = await api.calculateIndicator({
          indicator: ind.name,
          period: ind.period,
          timeframe: ind.timeframe,
          history: Math.ceil(candleCount * (TF_MINUTES[timeframe] ?? 5) / (TF_MINUTES[ind.timeframe] ?? 5)) + ind.period,
          pair,
          broker_name: brokerName,
          ...(ind.smoothPeriod && ind.smoothPeriod > 1 ? { smooth_period: ind.smoothPeriod } : {}),
        })
        if (ind.name === 'BB') {
          type BBRaw = { timestamp: string; value: { upper: number; middle: number; lower: number } }
          const raw = result.values as unknown as BBRaw[]
          return {
            ...ind,
            bbData: {
              upper: raw.map(v => ({ timestamp: v.timestamp, value: v.value.upper })),
              middle: raw.map(v => ({ timestamp: v.timestamp, value: v.value.middle })),
              lower: raw.map(v => ({ timestamp: v.timestamp, value: v.value.lower })),
            },
            data: raw.map(v => ({ timestamp: v.timestamp, value: v.value.middle })),
          }
        }
        return { ...ind, data: result.values }
      } catch {
        return ind
      }
    }))

    return results
  }, [candleCount, pair, timeframe, brokerName])

  // ── Data loading ───────────────────────────────────────────────────────────

  const loadData = useCallback(async () => {
    if (!pair) return
    setLoading(true)
    setError(null)
    try {
      const [newCandles, analyses] = await Promise.all([
        api.getCandles(pair, timeframe, candleCount, brokerName),
        api.getAnalyses({ pair, limit: 300 }),
      ])
      setCandles(newCandles)
      setAnalysisRecords(analyses)
      const updated = await recomputeIndicators(newCandles, indicatorsRef.current)
      setIndicators(updated)

      // Load DXY per-candle data silently (does not block chart load)
      api.calculateIndicator({
        indicator: 'DXY',
        period: 14,
        timeframe,
        history: Math.min(candleCount, 100),
        pair,
        broker_name: brokerName,
      }).then(r => {
        type DXYRaw = { timestamp: string; value: DXYEntry }
        const raw = r.values as unknown as DXYRaw[]
        const map: Record<number, DXYEntry> = {}
        for (const v of raw) map[Math.floor(new Date(v.timestamp).getTime() / 1000)] = v.value
        setDxyData(map)
      }).catch(() => setDxyData({}))
    } catch (err) {
      setError(String(err))
    } finally {
      setLoading(false)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pair, timeframe, candleCount, brokerName])

  useEffect(() => { void loadData() }, [loadData])

  // Auto-refresh every 30 seconds
  useEffect(() => {
    const id = setInterval(() => { void loadData() }, 30_000)
    return () => clearInterval(id)
  }, [loadData])

  // ── Swing levels ───────────────────────────────────────────────────────────

  const loadSwingLevels = useCallback(async () => {
    if (!pair || !swingEnabled) { setSwingLines([]); return }
    setSwingLoading(true)
    try {
      const baseCount = swingVisibleOnly ? visibleCandleCount : candleCount
      const chartMinutes = baseCount * (TF_MINUTES[timeframe] ?? 5)
      const swingLookback = Math.max(10, Math.ceil(chartMinutes / (TF_MINUTES[swingTf] ?? 60)))
      const res = await api.executeTool('get_swing_levels', { timeframe: swingTf, max_levels: swingCount, lookback: swingLookback, atr_period: swingAtrPeriod, min_gap_atr: swingMinGapAtr, price_source: swingPriceSource, sort_by: swingSortByRef.current }, null, brokerName, null, pair)
      type SwingLevel = { price: number; timestamp: string; distance: number }
      type SwingResult = { highs: SwingLevel[]; lows: SwingLevel[]; confluence: SwingLevel[] }
      const result = res.result as SwingResult
      const lines: ForexChartPriceLine[] = [
        ...(result.highs ?? []).map(h => ({
          price: h.price,
          title: `SH ${h.price.toFixed(5)}`,
          color: '#10b981',
          lineStyle: swingLineStyle,
          lineWidth: swingLineWidth,
        })),
        ...(result.lows ?? []).map(l => ({
          price: l.price,
          title: `SL ${l.price.toFixed(5)}`,
          color: '#ef4444',
          lineStyle: swingLineStyle,
          lineWidth: swingLineWidth,
        })),
        ...(result.confluence ?? []).map(c => ({
          price: c.price,
          title: `SH/SL ${c.price.toFixed(5)}`,
          color: '#f97316',
          lineStyle: swingLineStyle,
          lineWidth: Math.min(swingLineWidth + 1, 4),
        })),
      ]
      setSwingLines(lines)
    } catch {
      setSwingLines([])
    } finally {
      setSwingLoading(false)
    }
  }, [pair, swingEnabled, swingTf, swingCount, swingAtrPeriod, swingMinGapAtr, candleCount, visibleCandleCount, swingVisibleOnly, timeframe, swingLineWidth, swingLineStyle, swingPriceSource, brokerName])

  useEffect(() => { void loadSwingLevels() }, [loadSwingLevels])

  // ── Analyst markers ────────────────────────────────────────────────────────

  const analysisMarkers: ForexChartMarker[] = useMemo(() => {
    if (!showAnalyses || candles.length === 0) return []
    const tfMs = (TF_MINUTES[timeframe] ?? 5) * 60 * 1000
    const minTs = new Date(candles[0].timestamp).getTime()
    const maxTs = new Date(candles[candles.length - 1].timestamp).getTime() + tfMs
    // Only include analyses within the loaded candle range, one per candle bucket
    const buckets = new Map<number, typeof analysisRecords[number]>()
    for (const rec of analysisRecords) {
      const ts = new Date(rec.decided_at).getTime()
      if (ts < minTs || ts > maxTs) continue
      const bucket = Math.floor(ts / tfMs)
      const existing = buckets.get(bucket)
      if (!existing || ts > new Date(existing.decided_at).getTime()) {
        buckets.set(bucket, rec)
      }
    }
    return Array.from(buckets.entries()).map(([bucket, rec]) => ({
      timestamp: new Date(bucket * tfMs).toISOString(),
      position: 'aboveBar' as const,
      shape: rec.decision === 'BIAS_LONG' ? 'arrowUp' as const
           : rec.decision === 'BIAS_SHORT' ? 'arrowDown' as const
           : 'circle' as const,
      color: rec.decision === 'BIAS_LONG' ? '#10b981'
           : rec.decision === 'BIAS_SHORT' ? '#ef4444'
           : '#6b7280',
      text: rec.decision === 'BIAS_LONG' ? 'U' : rec.decision === 'BIAS_SHORT' ? 'D' : 'N',
      payload: rec,
    }))
  }, [showAnalyses, analysisRecords, timeframe],
  )

  // ── Chart overlay/oscillator props ─────────────────────────────────────────

  const overlayLines: ForexChartOverlayLine[] = useMemo(() => {
    const lines: ForexChartOverlayLine[] = []
    for (const ind of indicators) {
      if (!ind.visible) continue
      if (['RSI', 'ATR', 'SLOPE_E', 'SLOPE_S'].includes(ind.name)) continue
      if (ind.name === 'BB' && ind.bbData) {
        lines.push({ key: `${ind.id}_upper`,  label: `BB(${ind.period}) U`, color: ind.color, lineWidth: ind.lineWidth, lineStyle: ind.lineStyle, values: ind.bbData.upper })
        lines.push({ key: `${ind.id}_middle`, label: `BB(${ind.period}) M`, color: ind.color, lineWidth: ind.lineWidth, lineStyle: ind.lineStyle, values: ind.bbData.middle })
        lines.push({ key: `${ind.id}_lower`,  label: `BB(${ind.period}) L`, color: ind.color, lineWidth: ind.lineWidth, lineStyle: ind.lineStyle, values: ind.bbData.lower })
      } else {
        lines.push({
          key: ind.id,
          label: `${ind.name}(${ind.period})`,
          color: ind.color,
          lineWidth: ind.lineWidth,
          lineStyle: ind.lineStyle,
          values: ind.data,
        })
      }
    }
    return lines
  }, [indicators])

  const oscillators: ForexChartOscillator[] = useMemo(
    () => indicators
      .filter(ind => ind.visible && ['RSI', 'ATR', 'SLOPE_E', 'SLOPE_S'].includes(ind.name))
      .map(ind => ({
        key: ind.id,
        label: ind.name === 'SLOPE_E' ? `SlopeE(${ind.period}) pips/candle`
             : ind.name === 'SLOPE_S' ? `SlopeS(${ind.period}) pips/candle`
             : `${ind.name}(${ind.period})`,
        color: ind.color,
        lineWidth: ind.lineWidth,
        lineStyle: ind.lineStyle,
        precision: ind.name === 'RSI' ? 2 : (['SLOPE_E', 'SLOPE_S'] as string[]).includes(ind.name) ? 2 : 5,
        values: ind.data,
        zeroline: (['SLOPE_E', 'SLOPE_S'] as string[]).includes(ind.name),
      })),
    [indicators],
  )

  const sessionBands = useMemo(
    () => showSessionBands ? computeSessionBands(candles) : [],
    [showSessionBands, candles],
  )

  // ── Indicator management ───────────────────────────────────────────────────

  function addIndicator(name: IndicatorName) {
    const def = INDICATOR_DEFS.find(d => d.name === name)!
    const newInd: IndicatorInstance = {
      id: uid(),
      name,
      period: def.defaultPeriod,
      timeframe,
      color: DEFAULT_COLORS[indicators.length % DEFAULT_COLORS.length],
      lineStyle: LineStyle.Solid,
      lineWidth: 1,
      visible: true,
      data: [],
      // Slope indicators default to smooth_period=3 to reduce noise
      ...((['SLOPE_E', 'SLOPE_S'] as const).includes(name as 'SLOPE_E' | 'SLOPE_S') ? { smoothPeriod: 3 } : {}),
    }
    const updated = [...indicators, newInd]
    setIndicators(updated)
    void recomputeIndicators(candles, updated).then(setIndicators)
  }

  function removeIndicator(id: string) {
    setIndicators(prev => prev.filter(i => i.id !== id))
  }

  function updateIndicator(id: string, patch: Partial<IndicatorInstance>) {
    setIndicators(prev => {
      const updated = prev.map(i => i.id === id ? { ...i, ...patch } : i)
      if (recomputeTimerRef.current) clearTimeout(recomputeTimerRef.current)
      recomputeTimerRef.current = setTimeout(() => {
        void recomputeIndicators(candles, updated).then(setIndicators)
      }, 400)
      return updated
    })
  }

  // ── Drawing tool management ────────────────────────────────────────────────

  function startTool(tool: DrawingToolName) {
    if (activeTool === tool) {
      setActiveTool(null)
      chartRef.current?.cancelDrawing()
      setPendingClickCount(0)
      return
    }
    setActiveTool(tool)
    pendingElliottPointsRef.current = []
    setPendingClickCount(0)
    chartRef.current?.startDrawing(tool, activeDrawingStyle)
  }

  function handleDrawingComplete(drawing: Drawing) {
    setDrawings(prev => [...prev, drawing])
    setPendingClickCount(0)
    if (multiUseRef.current && activeToolRef.current) {
      chartRef.current?.startDrawing(activeToolRef.current, activeDrawingStyleRef.current)
    } else {
      setActiveTool(null)
    }
  }

  function finalizeElliott() {
    const pts = pendingElliottPointsRef.current
    if (pts.length < 2) return
    const baseLabels = elliottMode === 'impulse'
      ? ['1', '2', '3', '4', '5', 'a', 'b', 'c', 'd']
      : ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I']
    const labels = baseLabels.slice(0, pts.length)
    const drawing: Drawing = {
      id: uid(),
      tool: 'elliott',
      points: pts.map(p => ({ price: p.price, time: p.time as unknown as import('lightweight-charts').UTCTimestamp })),
      style: activeDrawingStyle,
      elliottLabels: labels,
      visible: true,
      selected: false,
    }
    chartRef.current?.cancelDrawing()
    chartRef.current?.addDrawing(drawing)
    setDrawings(prev => [...prev, drawing])
    setPendingClickCount(0)
    pendingElliottPointsRef.current = []
    if (multiUseRef.current) {
      chartRef.current?.startDrawing('elliott', activeDrawingStyleRef.current)
    } else {
      setActiveTool(null)
    }
  }

  function undoLastDrawing() {
    setDrawings(prev => {
      if (prev.length === 0) return prev
      const last = prev[prev.length - 1]
      chartRef.current?.removeDrawing(last.id)
      return prev.slice(0, -1)
    })
  }

  function removeDrawing(id: string) {
    chartRef.current?.removeDrawing(id)
    setDrawings(prev => prev.filter(d => d.id !== id))
  }

  function toggleDrawingVisible(id: string) {
    const d = drawings.find(x => x.id === id)
    if (!d) return
    const updated = { ...d, visible: !d.visible }
    chartRef.current?.updateDrawing(id, { visible: updated.visible })
    setDrawings(prev => prev.map(x => x.id === id ? updated : x))
  }

  function updateDrawingPoints(id: string, points: Drawing['points']) {
    chartRef.current?.updateDrawing(id, { points })
    setDrawings(prev => prev.map(x => x.id === id ? { ...x, points } : x))
  }

  function updateDrawingLabel(id: string, label: string) {
    chartRef.current?.updateDrawing(id, { label })
    setDrawings(prev => prev.map(x => x.id === id ? { ...x, label } : x))
  }

  function updateDrawingStyle(id: string, patch: Partial<Drawing['style']>) {
    const d = drawings.find(x => x.id === id)
    if (!d) return
    const style = { ...d.style, ...patch }
    chartRef.current?.updateDrawing(id, { style })
    setDrawings(prev => prev.map(x => x.id === id ? { ...x, style } : x))
  }

  // ── Print ──────────────────────────────────────────────────────────────────

  function executePrint() {
    const chartImg = printOpts.chart ? chartRef.current?.captureImageForPrint() ?? null : null

    const candleRows = printOpts.candle && selectedCandle
      ? `<tr><td>Time</td><td>${selectedCandle.timestamp}</td></tr>
         <tr><td>Open</td><td>${selectedCandle.open.toFixed(5)}</td></tr>
         <tr><td>High</td><td>${selectedCandle.high.toFixed(5)}</td></tr>
         <tr><td>Low</td><td>${selectedCandle.low.toFixed(5)}</td></tr>
         <tr><td>Close</td><td>${selectedCandle.close.toFixed(5)}</td></tr>
         <tr><td>Volume</td><td>${selectedCandle.tick_volume}</td></tr>`
      : ''

    const indRows = printOpts.candle && selectedCandle
      ? indicators.filter(i => i.visible).map(ind => {
          const ts = new Date(selectedCandle.timestamp).getTime() / 1000
          const v = ind.data.find(d => Math.floor(new Date(d.timestamp).getTime() / 1000) === ts)
          return v ? `<tr><td>${ind.name}(${ind.period})</td><td>${v.value.toFixed(5)}</td></tr>` : ''
        }).join('')
      : ''

    const analysisHtml = printOpts.analysis && selectedAnalysis
      ? `<div style="page-break-before:always">
           <h2>Analyst Analysis</h2>
           <p>${selectedAnalysis.pair ?? '-'} · ${selectedAnalysis.decision ?? '-'} · ${selectedAnalysis.decided_at}</p>
           <pre>${(selectedAnalysis.analysis_text ?? JSON.stringify(selectedAnalysis.output, null, 2)).replace(/</g, '&lt;').replace(/>/g, '&gt;')}</pre>
         </div>`
      : ''

    const html = `<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <title>Chart Analysis ${pair} ${timeframe}</title>
    <style>
      body { font-family: Arial, sans-serif; color: #111827; margin: 24px; }
      h1, h2 { margin: 0 0 10px; }
      table { border-collapse: collapse; margin: 10px 0; }
      td { padding: 4px 12px 4px 0; font-size: 13px; }
      td:first-child { color: #6b7280; font-size: 12px; text-transform: uppercase; }
      .chart img { width: 100%; border: 1px solid #d1d5db; border-radius: 8px; margin: 12px 0; }
      pre { white-space: pre-wrap; word-break: break-word; background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 8px; padding: 12px; font-size: 12px; line-height: 1.5; }
      @media print { body { margin: 12px; } }
    </style>
  </head>
  <body>
    <h1>Chart Analysis — ${pair} / ${timeframe}</h1>
    ${chartImg ? `<div class="chart"><img src="${chartImg}" alt="Chart" /></div>` : ''}
    ${candleRows ? `<h2>Selected Candle</h2><table>${candleRows}${indRows}</table>` : ''}
    ${analysisHtml}
    <script>window.onload = () => window.print();</script>
  </body>
</html>`

    const w = window.open('', '_blank', 'width=1200,height=900')
    if (w) {
      w.document.open()
      w.document.write(html)
      w.document.close()
    }
    setShowPrintDialog(false)
  }

  // ── KB Import ─────────────────────────────────────────────────────────────

  const handleKbImport = useCallback(async () => {
    const chartImage = chartRef.current?.captureImage() ?? null

    const indicatorLines = indicators.filter(i => i.visible).map(ind => {
      const lastVal = ind.data.length > 0 ? ind.data[ind.data.length - 1].value : null
      return `- ${ind.name}(${ind.period}) [${ind.timeframe}]: ${lastVal !== null ? lastVal.toFixed(5) : '–'}`
    }).join('\n') || '- –'

    const swingLevelLines = swingEnabled && swingLines.length > 0
      ? swingLines.map(l => `- ${l.title}: ${l.price.toFixed(5)}`).join('\n')
      : '- –'

    const pipSize = selectedCandle && Math.max(selectedCandle.high, selectedCandle.open) > 20 ? 0.01 : 0.0001
    const toPips = (v: number) => (v / pipSize).toFixed(1)

    const candleSection = selectedCandle
      ? `## Selected Candle
| | | | |
|---|---|---|---|
| Time | ${selectedCandle.timestamp} | Open | ${selectedCandle.open.toFixed(5)} |
| OC | ${toPips(Math.abs(selectedCandle.close - selectedCandle.open))} | High | ${selectedCandle.high.toFixed(5)} |
| HL | ${toPips(selectedCandle.high - selectedCandle.low)} | Low | ${selectedCandle.low.toFixed(5)} |
| Volume | ${selectedCandle.tick_volume} | Close | ${selectedCandle.close.toFixed(5)} |
`
      : ''

    const analysisSection = selectedAnalysis
      ? `## Analyst Analysis
**Pair:** ${selectedAnalysis.pair ?? '–'} · **Decision:** ${selectedAnalysis.decision ?? '–'} · **At:** ${selectedAnalysis.decided_at}

\`\`\`
${selectedAnalysis.analysis_text ?? JSON.stringify(selectedAnalysis.output, null, 2)}
\`\`\`
`
      : ''

    const md = `# Chart Analysis — ${pair} / ${timeframe}

**Broker:** ${brokerName ?? '–'} · **Candles:** ${candleCount}
${chartImage ? `\n## Chart\n<img src="${chartImage}" style="width:100%" />\n` : ''}
${candleSection}
## Indicators
${indicatorLines}

## Swing Levels
${swingLevelLines}

${analysisSection}`

    try {
      await kbImport('ChartAnalysis', md)
      setKbMsg('✓ In Knowledgebase gespeichert')
      setTimeout(() => setKbMsg(null), 2000)
    } catch (e) {
      setError(`KB Import failed: ${String(e)}`)
    }
  }, [pair, timeframe, brokerName, candleCount, indicators, swingEnabled, swingLines, selectedCandle, selectedAnalysis])

  // ── Render ─────────────────────────────────────────────────────────────────

  const requiredForActive = activeTool ? (REQUIRED_POINTS[activeTool] ?? elliottCount) : 0

  return (
    <div className="flex flex-col h-full overflow-hidden bg-gray-950">

      {/* Top bar */}
      <div className="flex items-center gap-3 px-3 py-2 bg-gray-900 border-b border-gray-700 flex-shrink-0 flex-wrap">
        {/* Pair */}
        <select
          value={pair}
          onChange={e => setPair(e.target.value)}
          className="bg-gray-800 border border-gray-600 rounded px-2 py-1 text-gray-200 text-xs"
        >
          {availablePairs.length === 0 && <option value="">Loading…</option>}
          {availablePairs.map(p => <option key={p} value={p}>{p}</option>)}
        </select>

        {/* Broker */}
        {brokers.length > 1 ? (
          <select
            value={brokerName ?? ''}
            onChange={e => setBrokerName(e.target.value || null)}
            className="bg-gray-800 border border-gray-600 rounded px-2 py-1 text-gray-200 text-xs"
          >
            {brokers.map(b => (
              <option key={b.name} value={b.name}>{b.short_name ?? b.name}</option>
            ))}
          </select>
        ) : brokers.length === 1 ? (
          <span className="text-xs text-gray-400 border border-gray-700 rounded px-2 py-0.5 bg-gray-800">
            {brokers[0].short_name ?? brokers[0].name}
          </span>
        ) : null}

        {/* Timeframe */}
        <div className="flex items-center gap-1">
          {TIMEFRAMES.map(tf => (
            <button
              key={tf}
              onClick={() => setTimeframe(tf)}
              className={[
                'px-2 py-0.5 rounded border text-xs',
                timeframe === tf
                  ? 'bg-emerald-800/40 border-emerald-500 text-emerald-300'
                  : 'bg-gray-900 border-gray-700 text-gray-400 hover:text-gray-200',
              ].join(' ')}
            >{tf}</button>
          ))}
        </div>

        {/* Candle count */}
        <div className="flex items-center gap-1 text-xs text-gray-400">
          <span>Candles</span>
          <input
            type="number"
            min={20}
            max={2000}
            value={candleCount}
            onChange={e => setCandleCount(Math.max(20, Math.min(2000, Number(e.target.value))))}
            className="w-16 bg-gray-800 border border-gray-600 rounded px-1 py-0.5 text-gray-200 text-xs"
          />
        </div>

        {/* Reload */}
        <button
          onClick={() => void loadData()}
          disabled={loading}
          className="px-2 py-1 rounded border border-gray-700 bg-gray-900 text-gray-300 hover:text-white text-xs flex items-center gap-1"
        >
          <RefreshCcw className={`w-3 h-3 ${loading ? 'animate-spin' : ''}`} />
          {loading ? 'Loading…' : 'Reload'}
        </button>

        {error && <span className="text-xs text-red-400 truncate max-w-48">{error}</span>}

        {/* Active tool indicator */}
        {activeTool && (
          <span className="text-xs text-amber-400 border border-amber-700 rounded px-2 py-0.5 bg-amber-900/20">
            Drawing: {TOOL_LABELS[activeTool]}
            {requiredForActive > 1 && ` (${pendingClickCount}/${requiredForActive} pts)`}
            <button
              className="ml-2 text-amber-300 hover:text-white"
              onClick={() => { setActiveTool(null); chartRef.current?.cancelDrawing(); setPendingClickCount(0) }}
            >✕</button>
          </span>
        )}
        {activeTool === 'elliott' && (
          <button
            onClick={finalizeElliott}
            className="text-xs px-2 py-0.5 rounded bg-emerald-700 text-white hover:bg-emerald-600"
          >Done</button>
        )}

        <div className="ml-auto flex items-center gap-2">
          <button
            onClick={() => setPanMode(m => !m)}
            className={`px-2 py-1 rounded border text-xs flex items-center gap-1 ${
              panMode
                ? 'border-blue-500 bg-blue-900/40 text-blue-300'
                : 'border-gray-700 bg-gray-900 text-gray-400 hover:text-white'
            }`}
          >
            {panMode ? '✋ Pan' : '🔍 Zoom'}
          </button>
          <label className="flex items-center gap-1.5 cursor-pointer select-none text-xs text-gray-400 hover:text-gray-200">
            <input
              type="checkbox"
              checked={showSessionBands}
              onChange={e => setShowSessionBands(e.target.checked)}
              className="accent-blue-500"
            />
            Sessions
          </label>
          <label className="flex items-center gap-1.5 cursor-pointer select-none text-xs text-gray-400 hover:text-gray-200">
            <input
              type="checkbox"
              checked={showAnalyses}
              onChange={e => setShowAnalyses(e.target.checked)}
              className="accent-emerald-500"
            />
            Analyst
          </label>
          <button
            onClick={() => setShowPrintDialog(true)}
            className="px-2 py-1 rounded border border-gray-700 bg-gray-900 text-gray-300 hover:text-white text-xs flex items-center gap-1"
          >
            <Printer className="w-3 h-3" /> Print
          </button>
          {kbMsg
            ? <span className="text-xs text-emerald-400 border border-emerald-700 rounded px-2 py-0.5 bg-emerald-900/20">{kbMsg}</span>
            : <button
                onClick={() => void handleKbImport()}
                className="px-2 py-1 rounded border border-gray-700 bg-gray-900 text-gray-300 hover:text-white text-xs flex items-center gap-1"
                title="In Knowledgebase [Import] speichern"
              >
                <BookOpen className="w-3 h-3" /> → KB
              </button>
          }
        </div>
      </div>

      {/* Chart */}
      <div className="flex-1 min-h-0 p-2">
        <ForexChart
          ref={chartRef}
          candles={candles}
          sessionBands={sessionBands}
          futureBars={computeFutureBars(timeframe)}
          overlayLines={overlayLines}
          oscillators={oscillators}
          markers={analysisMarkers}
          priceLines={swingLines}
          ranges={[50, 100, 200, 500]}
          initialRange={candleCount}
          panMode={panMode}
          onRangeChange={n => { setCandleCount(n); setVisibleCandleCount(n) }}
          onMarkerSelect={marker => { if (marker.payload) { setSelectedAnalysis(marker.payload as AnalysisRecord); setShowAnalysisModal(true) } }}
          onCandleClick={candle => {
            setSelectedCandle(candle)
            // Find the analysis in the same candle bucket (same M5/H1/… period)
            const tfMs = (TF_MINUTES[timeframe] ?? 5) * 60 * 1000
            const candleBucket = Math.floor(new Date(candle.timestamp).getTime() / tfMs)
            const match = analysisRecords
              .filter(r => Math.floor(new Date(r.decided_at).getTime() / tfMs) === candleBucket)
              .sort((a, b) => new Date(b.decided_at).getTime() - new Date(a.decided_at).getTime())[0]
            setSelectedAnalysis(showAnalyses ? (match ?? null) : null)
          }}
          onDrawingComplete={drawing => { handleDrawingComplete(drawing) }}
          onPendingPoint={(_tool, points) => {
            pendingElliottPointsRef.current = points.map(p => ({ price: p.price, time: p.time as number }))
            setPendingClickCount(points.length)
          }}
        />
      </div>

      {/* Resize handle */}
      <div
        onMouseDown={e => {
          resizingRef.current = true
          resizeStartYRef.current = e.clientY
          resizeStartHeightRef.current = bottomHeight
          e.preventDefault()
        }}
        className="h-1.5 flex-shrink-0 cursor-row-resize bg-gray-700 hover:bg-emerald-600 transition-colors flex items-center justify-center"
      >
        <div className="w-12 h-0.5 bg-gray-500 rounded-full pointer-events-none" />
      </div>

      {/* Bottom section */}
      <div
        className="flex flex-shrink-0 overflow-hidden border-t border-gray-700"
        style={{ height: bottomHeight }}
      >
        {/* Left column: Indicators + Swing */}
        <div className="flex-1 overflow-y-auto border-r border-gray-700 p-3 space-y-4 text-xs min-w-0">
          <IndicatorsPanel
            indicators={indicators}
            onAdd={addIndicator}
            onRemove={removeIndicator}
            onUpdate={updateIndicator}
          />
          <SwingLevelsPanel
            enabled={swingEnabled}
            onToggle={() => setSwingEnabled(v => !v)}
            timeframe={swingTf}
            onTimeframeChange={setSwingTf}
            count={swingCount}
            onCountChange={setSwingCount}
            atrPeriod={swingAtrPeriod}
            onAtrPeriodChange={setSwingAtrPeriod}
            minGapAtr={swingMinGapAtr}
            onMinGapAtrChange={setSwingMinGapAtr}
            lineWidth={swingLineWidth}
            onLineWidthChange={setSwingLineWidth}
            lineStyle={swingLineStyle}
            onLineStyleChange={setSwingLineStyle}
            priceSource={swingPriceSource}
            onPriceSourceChange={setSwingPriceSource}
            visibleOnly={swingVisibleOnly}
            onVisibleOnlyChange={setSwingVisibleOnly}
            sortBy={swingSortBy}
            onSortByChange={(s) => { swingSortByRef.current = s; setSwingSortBy(s); void loadSwingLevels() }}
            loading={swingLoading}
            onReload={() => void loadSwingLevels()}
            lines={swingLines}
          />
        </div>

        {/* Middle column: Drawing tools */}
        <div className="flex-1 overflow-y-auto border-r border-gray-700 p-3 text-xs min-w-0">
          <DrawingToolsPanel
            activeTool={activeTool}
            onStartTool={startTool}
            activeStyle={activeDrawingStyle}
            onStyleChange={s => { setActiveDrawingStyle(s); activeDrawingStyleRef.current = s }}
            multiUse={multiUse}
            onMultiUseChange={setMultiUse}
            onUndoLast={undoLastDrawing}
            drawings={drawings}
            onRemoveDrawing={removeDrawing}
            onToggleVisible={toggleDrawingVisible}
            onUpdatePoints={updateDrawingPoints}
            onUpdateLabel={updateDrawingLabel}
            onUpdateStyle={updateDrawingStyle}
            elliottCount={elliottCount}
            onElliottCountChange={setElliottCount}
            elliottMode={elliottMode}
            onElliottModeChange={setElliottMode}
          />
        </div>

        {/* Right column: Candle data + Analyst */}
        <div className="w-72 flex-shrink-0 overflow-y-auto p-3 space-y-3 text-xs">
          <CandleDataPanel candle={selectedCandle} indicators={indicators} dxyData={dxyData} />
          <AnalystPanel
            showAnalyses={showAnalyses}
            onToggle={() => setShowAnalyses(v => !v)}
            selectedAnalysis={selectedAnalysis}
            onOpen={() => { if (selectedAnalysis) setShowAnalysisModal(true) }}
          />
        </div>
      </div>

      {/* Analysis modal */}
      {showAnalysisModal && selectedAnalysis && (
        <div className="fixed inset-0 z-50 bg-black/70 flex items-center justify-center p-6">
          <div className="w-full max-w-5xl max-h-[85vh] bg-gray-950 border border-gray-700 rounded-xl overflow-hidden flex flex-col">
            <div className="px-5 py-4 border-b border-gray-800 flex items-center justify-between">
              <div>
                <h3 className="text-base font-semibold text-gray-100">AA Recommendation</h3>
                <p className="text-sm text-gray-400">
                  {selectedAnalysis.pair ?? '-'} · {selectedAnalysis.decision ?? '-'} · {selectedAnalysis.decided_at}
                </p>
              </div>
              <button
                onClick={() => setShowAnalysisModal(false)}
                className="px-3 py-1 rounded border border-gray-700 bg-gray-900 text-gray-300 hover:text-white text-sm"
              >Close</button>
            </div>
            <div className="flex-1 overflow-auto p-5 space-y-4">
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">
                {[
                  ['Decision', selectedAnalysis.decision ?? '-'],
                  ['Confidence', typeof selectedAnalysis.confidence === 'number' ? selectedAnalysis.confidence.toFixed(2) : '-'],
                  ['Order Start', selectedAnalysis.order_start_signal ?? '-'],
                  ['Entry Quality', selectedAnalysis.entry_quality ?? '-'],
                ].map(([label, value]) => (
                  <div key={label} className="rounded border border-gray-800 bg-gray-900/40 p-3">
                    <div className="text-gray-500">{label}</div>
                    <div className="text-gray-100 mt-1">{value}</div>
                  </div>
                ))}
              </div>
              <div className="space-y-1">
                <div className="flex items-center justify-between">
                  <span className="text-xs text-gray-500">Decision JSON</span>
                  <CopyButton getText={() => selectedAnalysis.analysis_text ?? JSON.stringify(selectedAnalysis.analysis ?? selectedAnalysis.output, null, 2)} />
                </div>
                <pre className="whitespace-pre-wrap break-words text-sm text-gray-200 leading-6">
                  {selectedAnalysis.analysis_text ?? JSON.stringify(selectedAnalysis.analysis ?? selectedAnalysis.output, null, 2)}
                </pre>
              </div>
              <div className="rounded border border-gray-800 bg-gray-900/40 p-4 space-y-3">
                <div className="flex items-center justify-between">
                  <h4 className="text-sm font-medium text-gray-200">Decision Snapshot</h4>
                  {selectedAnalysis.market_snapshot && (
                    <CopyButton getText={() => JSON.stringify(selectedAnalysis.market_snapshot, null, 2)} />
                  )}
                </div>
                <pre className="whitespace-pre-wrap break-words text-xs text-gray-300 leading-6">
                  {JSON.stringify(selectedAnalysis.market_snapshot ?? {}, null, 2)}
                </pre>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Print dialog */}
      {showPrintDialog && (
        <div className="fixed inset-0 z-50 bg-black/70 flex items-center justify-center">
          <div className="bg-gray-900 border border-gray-700 rounded-xl p-6 w-80 space-y-4">
            <h3 className="text-base font-semibold text-gray-100">Print / Export PDF</h3>
            <div className="space-y-3 text-sm text-gray-300">
              {[
                { key: 'chart', label: 'Chart (current view)' },
                { key: 'candle', label: 'Selected candle data + indicators' },
                { key: 'analysis', label: 'Analyst analysis (last selected)' },
              ].map(({ key, label }) => (
                <label key={key} className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={printOpts[key as keyof typeof printOpts]}
                    onChange={e => setPrintOpts(prev => ({ ...prev, [key]: e.target.checked }))}
                    className="accent-emerald-500"
                  />
                  {label}
                </label>
              ))}
            </div>
            <div className="flex gap-2 justify-end pt-2">
              <button
                onClick={() => setShowPrintDialog(false)}
                className="px-3 py-1.5 rounded border border-gray-700 text-gray-300 text-sm hover:text-white"
              >Cancel</button>
              <button
                onClick={executePrint}
                className="px-3 py-1.5 rounded bg-emerald-700 text-white text-sm hover:bg-emerald-600 flex items-center gap-1"
              >
                <Printer className="w-3.5 h-3.5" /> Print
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

// ── Sub-components ────────────────────────────────────────────────────────────

function IndicatorsPanel({
  indicators,
  onAdd,
  onRemove,
  onUpdate,
}: {
  indicators: IndicatorInstance[]
  onAdd: (name: IndicatorName) => void
  onRemove: (id: string) => void
  onUpdate: (id: string, patch: Partial<IndicatorInstance>) => void
}) {
  const [expanded, setExpanded] = useState(true)

  return (
    <div>
      <div
        className="flex items-center justify-between cursor-pointer mb-2"
        onClick={() => setExpanded(v => !v)}
      >
        <span className="font-semibold text-gray-300 text-xs uppercase tracking-wide">Indicators</span>
        <span className="text-gray-500">{expanded ? '▾' : '▸'}</span>
      </div>
      {expanded && (
        <div className="space-y-2">
          {/* Add buttons */}
          <div className="flex flex-wrap gap-1">
            {INDICATOR_DEFS.map(def => (
              <button
                key={def.name}
                onClick={() => onAdd(def.name)}
                className="flex items-center gap-0.5 px-2 py-0.5 rounded border border-gray-700 bg-gray-800 text-gray-300 hover:text-white text-xs"
              >
                <Plus className="w-2.5 h-2.5" />{def.label}
              </button>
            ))}
          </div>
          {/* Instance list */}
          {indicators.length === 0 && <p className="text-gray-500 text-xs">No indicators added.</p>}
          {indicators.map(ind => (
            <div key={ind.id} className="flex items-center gap-1.5 bg-gray-900 rounded px-2 py-1.5 border border-gray-800">
              <button onClick={() => onUpdate(ind.id, { visible: !ind.visible })} className="text-gray-400 hover:text-white">
                {ind.visible ? <Eye className="w-3 h-3" /> : <EyeOff className="w-3 h-3 opacity-40" />}
              </button>
              <input
                type="color"
                value={ind.color}
                onChange={e => onUpdate(ind.id, { color: e.target.value })}
                className="w-5 h-5 cursor-pointer rounded border-0 bg-transparent"
              />
              <span className="text-gray-300 font-medium w-10 shrink-0">{ind.name}</span>
              <input
                type="number"
                min={ind.name === 'VWAP' ? 0 : 1}
                max={500}
                value={ind.period}
                onChange={e => onUpdate(ind.id, { period: Number(e.target.value) })}
                className="w-14 bg-gray-800 border border-gray-700 rounded px-1 text-gray-200"
                title={ind.name === 'VWAP' ? 'Period (0 = daily reset from 00:00 UTC)' : 'Period'}
              />
              <select
                value={ind.timeframe}
                onChange={e => onUpdate(ind.id, { timeframe: e.target.value })}
                className="bg-gray-800 border border-gray-700 rounded px-1 text-gray-200"
              >
                {TIMEFRAMES.map(tf => <option key={tf} value={tf}>{tf}</option>)}
              </select>
              <select
                value={ind.lineStyle}
                onChange={e => onUpdate(ind.id, { lineStyle: Number(e.target.value) as LineStyle })}
                className="bg-gray-800 border border-gray-700 rounded px-1 text-gray-200 hidden sm:block"
              >
                {LINE_STYLE_OPTIONS.map(opt => (
                  <option key={opt.value} value={opt.value}>{opt.label}</option>
                ))}
              </select>
              <input
                type="number"
                min={1}
                max={4}
                value={ind.lineWidth}
                onChange={e => onUpdate(ind.id, { lineWidth: Number(e.target.value) })}
                className="w-8 bg-gray-800 border border-gray-700 rounded px-1 text-gray-200"
                title="Line width"
              />
              {(['SLOPE_E', 'SLOPE_S'] as string[]).includes(ind.name) && (
                <input
                  type="number"
                  min={1}
                  max={20}
                  value={ind.smoothPeriod ?? 1}
                  onChange={e => onUpdate(ind.id, { smoothPeriod: Number(e.target.value) })}
                  className="w-14 bg-gray-800 border border-amber-700 rounded px-1 text-amber-200"
                  title="Smooth period (EMA applied to slope)"
                />
              )}
              <button onClick={() => onRemove(ind.id)} className="text-gray-500 hover:text-red-400 ml-auto">
                <Trash2 className="w-3 h-3" />
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function tsToDatetimeLocal(ts: number): string {
  return new Date(ts * 1000).toISOString().slice(0, 16)
}

function datetimeLocalToTs(val: string): number {
  return Math.floor(new Date(val + ':00Z').getTime() / 1000)
}

function DrawingToolsPanel({
  activeTool,
  onStartTool,
  activeStyle,
  onStyleChange,
  multiUse,
  onMultiUseChange,
  onUndoLast,
  drawings,
  onRemoveDrawing,
  onToggleVisible,
  onUpdatePoints,
  onUpdateLabel,
  onUpdateStyle,
  elliottCount,
  onElliottCountChange,
  elliottMode,
  onElliottModeChange,
}: {
  activeTool: DrawingToolName | null
  onStartTool: (tool: DrawingToolName) => void
  activeStyle: DrawingStyle
  onStyleChange: (style: DrawingStyle) => void
  multiUse: boolean
  onMultiUseChange: (v: boolean) => void
  onUndoLast: () => void
  drawings: Drawing[]
  onRemoveDrawing: (id: string) => void
  onToggleVisible: (id: string) => void
  onUpdatePoints: (id: string, points: Drawing['points']) => void
  onUpdateLabel: (id: string, label: string) => void
  onUpdateStyle: (id: string, patch: Partial<Drawing['style']>) => void
  elliottCount: number
  onElliottCountChange: (n: number) => void
  elliottMode: 'impulse' | 'corrective'
  onElliottModeChange: (m: 'impulse' | 'corrective') => void
}) {
  const [expanded, setExpanded] = useState(true)
  const [expandedDrawingId, setExpandedDrawingId] = useState<string | null>(null)

  return (
    <div>
      <div
        className="flex items-center justify-between cursor-pointer mb-2"
        onClick={() => setExpanded(v => !v)}
      >
        <span className="font-semibold text-gray-300 text-xs uppercase tracking-wide">Drawing Tools</span>
        <span className="text-gray-500">{expanded ? '▾' : '▸'}</span>
      </div>
      {expanded && (
        <div className="space-y-3">
          {/* Style controls */}
          <div className="flex items-center gap-2 flex-wrap">
            <label className="flex items-center gap-1.5 cursor-pointer select-none text-xs text-gray-400 hover:text-gray-200">
              <input
                type="checkbox"
                checked={multiUse}
                onChange={e => onMultiUseChange(e.target.checked)}
                className="accent-amber-500"
              />
              Multi Use
            </label>
            <button
              onClick={onUndoLast}
              disabled={drawings.length === 0}
              className="flex items-center gap-1 px-1.5 py-0.5 rounded border border-gray-700 bg-gray-800 text-gray-400 hover:text-white disabled:opacity-30 disabled:cursor-not-allowed"
              title="Letztes Drawing entfernen"
            >
              <Undo2 className="w-3 h-3" />
            </button>
            <input
              type="color"
              value={activeStyle.color}
              onChange={e => onStyleChange({ ...activeStyle, color: e.target.value })}
              className="w-5 h-5 cursor-pointer rounded border-0 bg-transparent"
              title="Line color"
            />
            <select
              value={activeStyle.lineStyle}
              onChange={e => onStyleChange({ ...activeStyle, lineStyle: Number(e.target.value) as LineStyle })}
              className="bg-gray-800 border border-gray-700 rounded px-1 text-gray-200"
            >
              {LINE_STYLE_OPTIONS.map(opt => (
                <option key={opt.value} value={opt.value}>{opt.label}</option>
              ))}
            </select>
            <input
              type="number"
              min={1}
              max={4}
              value={activeStyle.lineWidth}
              onChange={e => onStyleChange({ ...activeStyle, lineWidth: Number(e.target.value) })}
              className="w-10 bg-gray-800 border border-gray-700 rounded px-1 text-gray-200"
              title="Line width"
            />
            <span className="text-gray-500">Fill</span>
            <input
              type="color"
              value={activeStyle.fillColor ?? activeStyle.color}
              onChange={e => onStyleChange({ ...activeStyle, fillColor: e.target.value })}
              className="w-5 h-5 cursor-pointer rounded border-0 bg-transparent"
              title="Fill color"
            />
            <input
              type="number"
              min={0}
              max={1}
              step={0.05}
              value={activeStyle.fillOpacity ?? 0.15}
              onChange={e => onStyleChange({ ...activeStyle, fillOpacity: Number(e.target.value) })}
              className="w-12 bg-gray-800 border border-gray-700 rounded px-1 text-gray-200"
              title="Fill opacity 0–1"
            />
          </div>

          {/* Tool buttons */}
          {TOOL_GROUPS.map(group => (
            <div key={group.label} className="space-y-1">
              <div className="text-gray-500 text-xs">{group.label}</div>
              <div className="flex flex-wrap gap-1">
                {group.tools.map(tool => (
                  <button
                    key={tool}
                    onClick={() => onStartTool(tool)}
                    className={[
                      'px-2 py-0.5 rounded border text-xs',
                      activeTool === tool
                        ? 'border-emerald-500 bg-emerald-900/40 text-emerald-300'
                        : 'border-gray-700 bg-gray-800 text-gray-300 hover:text-white',
                    ].join(' ')}
                  >
                    {TOOL_LABELS[tool]}
                  </button>
                ))}
              </div>
            </div>
          ))}

          {/* Elliott options when active */}
          {activeTool === 'elliott' && (
            <div className="flex items-center gap-2 flex-wrap pl-1">
              <span className="text-gray-400">Points:</span>
              <input
                type="number"
                min={3}
                max={9}
                value={elliottCount}
                onChange={e => onElliottCountChange(Number(e.target.value))}
                className="w-10 bg-gray-800 border border-gray-700 rounded px-1 text-gray-200"
              />
              <button
                onClick={() => onElliottModeChange('impulse')}
                className={`text-xs px-2 py-0.5 rounded border ${elliottMode === 'impulse' ? 'border-emerald-500 text-emerald-300' : 'border-gray-700 text-gray-400'}`}
              >1-2-3-4-5</button>
              <button
                onClick={() => onElliottModeChange('corrective')}
                className={`text-xs px-2 py-0.5 rounded border ${elliottMode === 'corrective' ? 'border-emerald-500 text-emerald-300' : 'border-gray-700 text-gray-400'}`}
              >A-B-C</button>
            </div>
          )}

          {/* Active drawings list */}
          {drawings.length > 0 && (
            <div className="space-y-1 pt-1 border-t border-gray-800">
              <div className="text-gray-500 text-xs mb-1">Active drawings</div>
              {[...drawings].reverse().map(d => {
                const isExp = expandedDrawingId === d.id
                return (
                <div key={d.id} className="bg-gray-900 rounded border border-gray-800">
                  {/* Row header */}
                  <div className="flex items-center gap-1.5 px-2 py-1">
                    <button onClick={() => onToggleVisible(d.id)} className="text-gray-400 hover:text-white flex-shrink-0">
                      {d.visible ? <Eye className="w-3 h-3" /> : <EyeOff className="w-3 h-3 opacity-40" />}
                    </button>
                    <div className="w-3 h-3 rounded-full flex-shrink-0" style={{ backgroundColor: d.style.color }} />
                    <span className="text-gray-300 flex-1 truncate">{TOOL_LABELS[d.tool]}</span>
                    <button
                      onClick={() => setExpandedDrawingId(isExp ? null : d.id)}
                      className="text-gray-500 hover:text-gray-200 px-1"
                      title="Edit points"
                    >
                      {isExp ? '▾' : '▸'}
                    </button>
                    <button onClick={() => onRemoveDrawing(d.id)} className="text-gray-500 hover:text-red-400 flex-shrink-0">
                      <Trash2 className="w-3 h-3" />
                    </button>
                  </div>
                  {/* Expanded style + point editors */}
                  {isExp && (
                    <div className="px-2 pb-2 space-y-1.5 border-t border-gray-800 pt-1.5">
                      {/* Style row */}
                      <div className="flex items-center gap-1.5 flex-wrap">
                        <input
                          type="color"
                          value={d.style.color}
                          onChange={e => onUpdateStyle(d.id, { color: e.target.value })}
                          className="w-5 h-5 cursor-pointer rounded border-0 bg-transparent flex-shrink-0"
                          title="Line color"
                        />
                        <select
                          value={d.style.lineStyle}
                          onChange={e => onUpdateStyle(d.id, { lineStyle: Number(e.target.value) as LineStyle })}
                          className="bg-gray-800 border border-gray-700 rounded px-1 text-gray-200 flex-shrink-0"
                          style={{ fontSize: '11px' }}
                        >
                          {LINE_STYLE_OPTIONS.map(opt => (
                            <option key={opt.value} value={opt.value}>{opt.label}</option>
                          ))}
                        </select>
                        <input
                          type="number"
                          min={1}
                          max={4}
                          value={d.style.lineWidth}
                          onChange={e => onUpdateStyle(d.id, { lineWidth: Number(e.target.value) })}
                          className="w-10 bg-gray-800 border border-gray-700 rounded px-1 text-gray-200 flex-shrink-0"
                          style={{ fontSize: '11px' }}
                          title="Line width"
                        />
                        {['rect', 'channel', 'fib_ret', 'fib_ext'].includes(d.tool) && (
                          <>
                            <input
                              type="color"
                              value={d.style.fillColor ?? d.style.color}
                              onChange={e => onUpdateStyle(d.id, { fillColor: e.target.value })}
                              className="w-5 h-5 cursor-pointer rounded border-0 bg-transparent flex-shrink-0"
                              title="Fill color"
                            />
                            <input
                              type="number"
                              min={0}
                              max={1}
                              step={0.05}
                              value={d.style.fillOpacity ?? 0.15}
                              onChange={e => onUpdateStyle(d.id, { fillOpacity: Number(e.target.value) })}
                              className="w-12 bg-gray-800 border border-gray-700 rounded px-1 text-gray-200 flex-shrink-0"
                              style={{ fontSize: '11px' }}
                              title="Fill opacity 0–1"
                            />
                          </>
                        )}
                      </div>
                      {d.tool === 'measure' && (
                        <div className="flex items-center gap-1">
                          <span className="text-gray-500 w-8 flex-shrink-0" style={{ fontSize: '10px' }}>Pos</span>
                          {(['top', 'middle', 'bottom'] as const).map(pos => (
                            <button
                              key={pos}
                              onClick={() => onUpdateLabel(d.id, pos)}
                              className={`px-1.5 py-0.5 rounded border text-xs ${(d.label ?? 'top') === pos ? 'border-emerald-500 bg-emerald-900/40 text-emerald-300' : 'border-gray-700 bg-gray-800 text-gray-400 hover:text-white'}`}
                            >{pos}</button>
                          ))}
                        </div>
                      )}
                      {d.tool === 'textlabel' && (
                        <>
                          <div className="flex items-center gap-1">
                            <span className="text-gray-500 w-8 flex-shrink-0" style={{ fontSize: '10px' }}>Text</span>
                            <input
                              type="text"
                              value={d.label ?? ''}
                              onChange={e => onUpdateLabel(d.id, e.target.value)}
                              placeholder="Label text… (| = neue Zeile)"
                              className="flex-1 min-w-0 bg-gray-800 border border-gray-700 rounded px-1 text-gray-200"
                              style={{ fontSize: '11px' }}
                            />
                          </div>
                          <div className="flex items-center gap-1">
                            <span className="text-gray-500 w-8 flex-shrink-0" style={{ fontSize: '10px' }}>Size</span>
                            <input
                              type="number"
                              min={8}
                              max={72}
                              value={d.style.fontSize ?? 12}
                              onChange={e => onUpdateStyle(d.id, { fontSize: Math.max(8, Math.min(72, Number(e.target.value))) })}
                              className="w-16 bg-gray-800 border border-gray-700 rounded px-1 text-gray-200"
                              style={{ fontSize: '11px' }}
                            />
                            <span className="text-gray-500" style={{ fontSize: '10px' }}>px</span>
                          </div>
                        </>
                      )}
                      {d.points.map((pt, i) => (
                        <div key={i} className="space-y-1">
                          <div className="text-gray-500" style={{ fontSize: '10px' }}>P{i + 1}</div>
                          <div className="flex items-center gap-1">
                            <span className="text-gray-500 w-8 flex-shrink-0" style={{ fontSize: '10px' }}>Price</span>
                            <input
                              type="number"
                              step="0.00001"
                              value={pt.price}
                              onChange={e => {
                                const newPoints = d.points.map((p, j) =>
                                  j === i ? { ...p, price: parseFloat(e.target.value) || p.price } : p
                                )
                                onUpdatePoints(d.id, newPoints)
                              }}
                              className="flex-1 min-w-0 bg-gray-800 border border-gray-700 rounded px-1 text-gray-200"
                              style={{ fontSize: '11px' }}
                            />
                          </div>
                          <div className="flex items-center gap-1">
                            <span className="text-gray-500 w-8 flex-shrink-0" style={{ fontSize: '10px' }}>Time</span>
                            <input
                              type="datetime-local"
                              value={tsToDatetimeLocal(pt.time)}
                              onChange={e => {
                                if (!e.target.value) return
                                const newPoints = d.points.map((p, j) =>
                                  j === i ? { ...p, time: datetimeLocalToTs(e.target.value) as UTCTimestamp } : p
                                )
                                onUpdatePoints(d.id, newPoints)
                              }}
                              className="flex-1 min-w-0 bg-gray-800 border border-gray-700 rounded px-1 text-gray-200"
                              style={{ fontSize: '11px' }}
                            />
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
                )
              })}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function CandleDataPanel({
  candle,
  indicators,
  dxyData,
}: {
  candle: CandleBar | null
  indicators: IndicatorInstance[]
  dxyData: Record<number, DXYEntry>
}) {
  if (!candle) {
    return (
      <div>
        <div className="font-semibold text-gray-300 text-xs uppercase tracking-wide mb-2">Candle Data</div>
        <p className="text-gray-500">Click a candle to view its data.</p>
      </div>
    )
  }
  const ts = Math.floor(new Date(candle.timestamp).getTime() / 1000)
  const dxy = dxyData[ts]
  const pipSize = Math.max(candle.high, candle.open) > 20 ? 0.01 : 0.0001
  const toPips = (v: number) => (v / pipSize).toFixed(1)

  return (
    <div>
      <div className="font-semibold text-gray-300 text-xs uppercase tracking-wide mb-2">Candle Data</div>
      <div className="space-y-0.5">
        {[
          ['Time',   candle.timestamp],
          ['Open',   candle.open.toFixed(5)],
          ['High',   candle.high.toFixed(5)],
          ['Low',    candle.low.toFixed(5)],
          ['Close',  candle.close.toFixed(5)],
          ['HL',     `${toPips(candle.high - candle.low)} p`],
          ['OC',     `${toPips(Math.abs(candle.close - candle.open))} p`],
          ['Volume', String(candle.tick_volume)],
          ['Spread', String(candle.spread)],
        ].map(([label, value]) => (
          <div key={label} className="flex gap-2">
            <span className="text-gray-500 w-14 flex-shrink-0">{label}</span>
            <span className="text-gray-200">{value}</span>
          </div>
        ))}
        {indicators.filter(i => i.visible).map(ind => {
          const v = ind.data.find(d => Math.floor(new Date(d.timestamp).getTime() / 1000) === ts)
          if (!v) return null
          return (
            <div key={ind.id} className="flex gap-2">
              <span className="text-gray-500 w-14 flex-shrink-0">{ind.name}({ind.period})</span>
              <span style={{ color: ind.color }}>{v.value.toFixed(5)}</span>
            </div>
          )
        })}
        {dxy && (
          <>
            <div className="pt-1 mt-0.5 border-t border-gray-800" />
            <div className="flex gap-2">
              <span className="text-gray-500 w-14 flex-shrink-0">DXY</span>
              <span className="text-gray-200">{dxy.dxy_close.toFixed(3)}</span>
            </div>
            <div className="flex gap-2">
              <span className="text-gray-500 w-14 flex-shrink-0">Direction</span>
              <span className={
                dxy.dxy_direction === 'UP'   ? 'text-emerald-400' :
                dxy.dxy_direction === 'DOWN' ? 'text-red-400' : 'text-gray-400'
              }>{dxy.dxy_direction}</span>
            </div>
            <div className="flex gap-2">
              <span className="text-gray-500 w-14 flex-shrink-0">Correl.</span>
              <span className="text-gray-200">{dxy.correlation.toFixed(3)}</span>
            </div>
          </>
        )}
      </div>
    </div>
  )
}

function AnalystPanel({
  showAnalyses,
  onToggle,
  selectedAnalysis,
  onOpen,
}: {
  showAnalyses: boolean
  onToggle: () => void
  selectedAnalysis: AnalysisRecord | null
  onOpen: () => void
}) {
  return (
    <div>
      <div className="flex items-center gap-2 mb-2">
        <label className="flex items-center gap-1.5 cursor-pointer">
          <input
            type="checkbox"
            checked={showAnalyses}
            onChange={onToggle}
            className="accent-emerald-500"
          />
          <span className="font-semibold text-gray-300 text-xs uppercase tracking-wide">Analyst View</span>
        </label>
      </div>
      {showAnalyses && (
        selectedAnalysis ? (
          <button
            onClick={onOpen}
            className="w-full text-left rounded px-2 py-1.5 border border-gray-700 bg-gray-900 hover:bg-gray-800 space-y-1"
          >
            <div className="flex items-center gap-2">
              <span className={`font-semibold ${
                selectedAnalysis.decision === 'BIAS_LONG' ? 'text-emerald-400'
                : selectedAnalysis.decision === 'BIAS_SHORT' ? 'text-red-400'
                : 'text-gray-400'
              }`}>
                {selectedAnalysis.decision ?? '-'}
              </span>
              {typeof selectedAnalysis.confidence === 'number' && (
                <span className="text-gray-500">{selectedAnalysis.confidence.toFixed(2)}</span>
              )}
            </div>
            <div className="text-gray-500">{selectedAnalysis.decided_at}</div>
            <div className="text-gray-500 italic">Click to open report…</div>
          </button>
        ) : (
          <p className="text-gray-600">Click a candle to see its analysis.</p>
        )
      )}
    </div>
  )
}

function SwingLevelsPanel({
  enabled,
  onToggle,
  timeframe,
  onTimeframeChange,
  count,
  onCountChange,
  atrPeriod,
  onAtrPeriodChange,
  minGapAtr,
  onMinGapAtrChange,
  lineWidth,
  onLineWidthChange,
  lineStyle,
  onLineStyleChange,
  priceSource,
  onPriceSourceChange,
  visibleOnly,
  onVisibleOnlyChange,
  sortBy,
  onSortByChange,
  loading,
  onReload,
  lines,
}: {
  enabled: boolean
  onToggle: () => void
  timeframe: string
  onTimeframeChange: (tf: string) => void
  count: number
  onCountChange: (n: number) => void
  atrPeriod: number
  onAtrPeriodChange: (n: number) => void
  minGapAtr: number
  onMinGapAtrChange: (n: number) => void
  lineWidth: number
  onLineWidthChange: (w: number) => void
  lineStyle: LineStyle
  onLineStyleChange: (s: LineStyle) => void
  priceSource: 'HL' | 'OC'
  onPriceSourceChange: (s: 'HL' | 'OC') => void
  visibleOnly: boolean
  onVisibleOnlyChange: (v: boolean) => void
  sortBy: 'nearest' | 'prominent'
  onSortByChange: (s: 'nearest' | 'prominent') => void
  loading: boolean
  onReload: () => void
  lines: ForexChartPriceLine[]
}) {
  return (
    <div>
      <div className="flex items-center gap-2 mb-2">
        <label className="flex items-center gap-1.5 cursor-pointer">
          <input
            type="checkbox"
            checked={enabled}
            onChange={onToggle}
            className="accent-emerald-500"
          />
          <span className="font-semibold text-gray-300 text-xs uppercase tracking-wide">Swing Levels</span>
        </label>
        {enabled && loading && <span className="text-gray-500 text-xs">Loading…</span>}
      </div>
      {enabled && (
        <div className="space-y-2">
          {/* Row 1: TF, Count, ATR, Gap */}
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-gray-400">TF</span>
            <select
              value={timeframe}
              onChange={e => onTimeframeChange(e.target.value)}
              className="bg-gray-800 border border-gray-700 rounded px-1 text-gray-200"
            >
              {Object.keys(TF_MINUTES).map(tf => (
                <option key={tf} value={tf}>{tf}</option>
              ))}
            </select>
            <span className="text-gray-400">Count</span>
            <input
              type="number" min={1} max={20} value={count}
              onChange={e => onCountChange(Number(e.target.value))}
              className="w-10 bg-gray-800 border border-gray-700 rounded px-1 text-gray-200"
            />
            <span className="text-gray-400">ATR</span>
            <input
              type="number" min={1} max={200} value={atrPeriod}
              onChange={e => onAtrPeriodChange(Math.max(1, Math.min(200, Number(e.target.value))))}
              className="w-12 bg-gray-800 border border-gray-700 rounded px-1 text-gray-200"
              title="ATR period for cluster gap"
            />
            <span className="text-gray-400">Gap</span>
            <input
              type="number" min={0} max={5} step={0.1} value={minGapAtr}
              onChange={e => onMinGapAtrChange(Math.max(0, Math.min(5, Number(e.target.value))))}
              className="w-12 bg-gray-800 border border-gray-700 rounded px-1 text-gray-200"
              title="Min gap as ATR multiple (0 = no clustering)"
            />
          </div>
          {/* Row 2: Next/Prominent, Visible/All, HL/OC */}
          <div className="flex items-center gap-2 flex-wrap">
            <div className="flex rounded border border-gray-700 overflow-hidden text-xs">
              {(['nearest', 'prominent'] as const).map(s => (
                <button key={s} onClick={() => onSortByChange(s)}
                  className={`px-2 py-0.5 ${sortBy === s ? 'bg-emerald-600 text-white' : 'bg-gray-800 text-gray-400 hover:text-white'}`}
                  title={s === 'nearest' ? 'Closest to current price' : 'Most visually prominent'}
                >
                  {s === 'nearest' ? 'Next' : 'Prominent'}
                </button>
              ))}
            </div>
            <div className="flex rounded border border-gray-700 overflow-hidden text-xs">
              {([['Visible', true], ['All', false]] as const).map(([lbl, val]) => (
                <button key={lbl} onClick={() => onVisibleOnlyChange(val)}
                  className={`px-2 py-0.5 ${visibleOnly === val ? 'bg-emerald-600 text-white' : 'bg-gray-800 text-gray-400 hover:text-white'}`}
                >
                  {lbl}
                </button>
              ))}
            </div>
            <div className="flex rounded border border-gray-700 overflow-hidden text-xs">
              {(['HL', 'OC'] as const).map(src => (
                <button key={src} onClick={() => onPriceSourceChange(src)}
                  className={`px-2 py-0.5 ${priceSource === src ? 'bg-emerald-600 text-white' : 'bg-gray-800 text-gray-400 hover:text-white'}`}
                >
                  {src}
                </button>
              ))}
            </div>
          </div>
          {/* Row 3: Width, Style, Reload */}
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-gray-400">Width</span>
            <input
              type="number" min={1} max={5} value={lineWidth}
              onChange={e => onLineWidthChange(Math.max(1, Math.min(5, Number(e.target.value))))}
              className="w-10 bg-gray-800 border border-gray-700 rounded px-1 text-gray-200"
            />
            <span className="text-gray-400">Style</span>
            <select
              value={lineStyle}
              onChange={e => onLineStyleChange(Number(e.target.value) as LineStyle)}
              className="bg-gray-800 border border-gray-700 rounded px-1 text-gray-200"
            >
              <option value={LineStyle.Solid}>Solid</option>
              <option value={LineStyle.Dashed}>Dashed</option>
              <option value={LineStyle.LargeDashed}>Large Dashed</option>
              <option value={LineStyle.Dotted}>Dotted</option>
              <option value={LineStyle.SparseDotted}>Sparse Dotted</option>
            </select>
            <button
              onClick={onReload}
              className="px-2 py-0.5 rounded border border-gray-700 bg-gray-800 text-gray-300 hover:text-white text-xs"
            >
              Reload
            </button>
          </div>
          {lines.length > 0 && (
            <div className="space-y-0.5 max-h-24 overflow-y-auto">
              {lines.map((l, i) => (
                <div key={i} className="flex items-center gap-1.5">
                  <div className="w-2 h-2 rounded-full flex-shrink-0" style={{ backgroundColor: l.color }} />
                  <span className="text-gray-400">{l.title}</span>
                </div>
              ))}
            </div>
          )}
          {lines.length === 0 && !loading && (
            <p className="text-gray-500 text-xs">No swing levels found.</p>
          )}
        </div>
      )}
    </div>
  )
}
