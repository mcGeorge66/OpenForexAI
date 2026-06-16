import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { TF_MINUTES } from '@/utils/indicators'
import { useDebounce } from '@/utils/useDebounce'
import { AlertCircle, Check, Copy, FileText, Printer, RefreshCcw, BookOpen } from 'lucide-react'
import { kbImport } from '@/knowledgebase/kbImport'
import { formatTs as formatTsCentral } from '@/utils/time'

import {
  api,
  type AnalysisRecord,
  type CandleBar,
  type IndicatorValue,
  type OrderbookEntryDetail,
  type OrderbookEntrySummary,
} from '@/api/client'
import {
  ForexChart,
  type ForexChartHandle,
  type ForexChartMarker,
  type ForexChartOscillator,
  type ForexChartOverlayLine,
  type ForexChartPriceLine,
} from '@/components/charts/ForexChart'

type StatusFilter = 'all' | 'open' | 'closed' | 'pending' | 'partially_filled' | 'rejected' | 'cancelled'
type ChartTimeframe = 'M5' | 'M15' | 'M30' | 'H1'

function CopyButton({ getText }: { getText: () => string }) {
  const [copied, setCopied] = useState(false)
  return (
    <button
      type="button"
      title="Copy to clipboard"
      onClick={() => { void navigator.clipboard.writeText(getText()).then(() => { setCopied(true); setTimeout(() => setCopied(false), 1500) }) }}
      className="inline-flex items-center text-gray-500 hover:text-gray-300 transition-colors"
    >
      {copied ? <Check className="w-3 h-3 text-emerald-400" /> : <Copy className="w-3 h-3" />}
    </button>
  )
}

function formatTs(value?: string | null, fallback = '-'): string {
  if (!value) return fallback
  const result = formatTsCentral(value)
  return result === '-' ? fallback : result
}

function formatMoney(value?: number | null): string {
  if (typeof value !== 'number' || Number.isNaN(value)) return '-'
  return value.toFixed(2)
}

function formatStake(value?: number | null): string {
  if (typeof value !== 'number' || Number.isNaN(value)) return '-'
  return value.toLocaleString('de-DE', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + ' $'
}

function formatResult(value?: number | null): string {
  if (typeof value !== 'number' || Number.isNaN(value)) return '-'
  return value.toFixed(2) + ' $'
}

function formatPrice(value?: number | null): string {
  if (typeof value !== 'number' || Number.isNaN(value)) return '-'
  return value.toFixed(5)
}

function getTradeStartAt(
  entry: Pick<OrderbookEntrySummary, 'requested_at' | 'opened_at'> | null | undefined,
): string | null {
  return entry?.opened_at ?? entry?.requested_at ?? null
}

function tradeDuration(entry: Pick<OrderbookEntrySummary, 'requested_at' | 'opened_at' | 'closed_at'> | null | undefined): string {
  const start = entry?.opened_at ?? entry?.requested_at
  const end = entry?.closed_at
  if (!start || !end) return '-'
  const mins = Math.round((new Date(end).getTime() - new Date(start).getTime()) / 60000)
  if (mins < 0) return '-'
  const hh = Math.floor(mins / 60).toString().padStart(2, '0')
  const mm = (mins % 60).toString().padStart(2, '0')
  return `${hh}:${mm}`
}

function getTradeEndAt(entry: Pick<OrderbookEntrySummary, 'closed_at'> | null | undefined): string | null {
  return entry?.closed_at ?? null
}

function getTradeEndDisplay(
  entry: Pick<OrderbookEntrySummary, 'status' | 'requested_at' | 'opened_at' | 'close_requested_at' | 'closed_at'> | null | undefined,
): string | null {
  if (!entry) return null
  if (entry.closed_at) return entry.closed_at
  if (entry.close_requested_at) return entry.close_requested_at
  if (entry.status === 'REJECTED' || entry.status === 'CANCELLED') {
    return getTradeStartAt(entry)
  }
  return null
}

function isTradeStartProvisional(
  entry: Pick<OrderbookEntrySummary, 'requested_at' | 'opened_at'> | null | undefined,
): boolean {
  if (!entry) return false
  return !entry.opened_at && !!entry.requested_at
}

function isTradeEndProvisional(
  entry: Pick<OrderbookEntrySummary, 'close_requested_at' | 'closed_at'> | null | undefined,
): boolean {
  if (!entry) return false
  return !entry.closed_at && !!entry.close_requested_at
}

function getCloseDisplay(
  entry: Pick<OrderbookEntrySummary, 'status' | 'close_reason'> | null | undefined,
): string {
  if (!entry) return '-'
  if (entry.close_reason) return entry.close_reason
  if (entry.status === 'REJECTED' || entry.status === 'CANCELLED') return entry.status
  if (entry.status === 'CLOSED') return 'closed'
  return 'running'
}

function findMarkerTimestamp(
  candles: CandleBar[],
  targetTimestamp: string | null,
  targetPrice?: number | null,
): string | null {
  if (!targetTimestamp || candles.length === 0) return candles[0]?.timestamp ?? null
  const targetMs = new Date(targetTimestamp).getTime()
  if (!Number.isFinite(targetMs)) return candles[0]?.timestamp ?? null

  const byTime = [...candles].sort(
    (left, right) =>
      Math.abs(new Date(left.timestamp).getTime() - targetMs) -
      Math.abs(new Date(right.timestamp).getTime() - targetMs),
  )
  const nearby = byTime.slice(0, Math.min(8, byTime.length))

  if (typeof targetPrice === 'number' && Number.isFinite(targetPrice)) {
    const containing = nearby.find(candle => candle.low <= targetPrice && candle.high >= targetPrice)
    if (containing) return containing.timestamp
  }

  return byTime[0]?.timestamp ?? candles[0]?.timestamp ?? null
}

function buildPriceLines(entry: OrderbookEntryDetail | null): ForexChartPriceLine[] {
  if (!entry) return []
  const overlays = entry.analysis_overlays?.levels ?? {}
  const lines: ForexChartPriceLine[] = []
  if (typeof entry.fill_price === 'number') {
    lines.push({ price: entry.fill_price, title: 'Entry', color: '#38bdf8' })
  } else {
    lines.push({ price: entry.requested_price, title: 'Requested', color: '#38bdf8' })
  }
  if (typeof entry.close_price === 'number') {
    lines.push({ price: entry.close_price, title: 'Exit', color: '#f59e0b' })
  }
  if (typeof entry.stop_loss === 'number') {
    lines.push({ price: entry.stop_loss, title: 'SL', color: '#ef4444' })
  }
  if (typeof entry.take_profit === 'number') {
    lines.push({ price: entry.take_profit, title: 'TP', color: '#22c55e' })
  }
  for (const value of overlays.support ?? []) {
    lines.push({ price: value, title: 'Support', color: '#14b8a6' })
  }
  for (const value of overlays.resistance ?? []) {
    lines.push({ price: value, title: 'Resistance', color: '#a855f7' })
  }
  return lines
}

function buildMarkers(entry: OrderbookEntryDetail | null, candles: CandleBar[]): ForexChartMarker[] {
  if (!entry || candles.length === 0) return []
  const entryPrice = entry.fill_price ?? entry.requested_price
  const requestedTime = findMarkerTimestamp(candles, getTradeStartAt(entry), entryPrice)
  const closedTime = findMarkerTimestamp(candles, getTradeEndAt(entry), entry.close_price)
  const markers: ForexChartMarker[] = []
  if (requestedTime) {
    markers.push({
      timestamp: requestedTime,
      position: entry.direction === 'BUY' ? 'belowBar' : 'aboveBar',
      shape: entry.direction === 'BUY' ? 'arrowUp' : 'arrowDown',
      color: '#38bdf8',
      text: 'Start',
    })
  }
  if (closedTime) {
    markers.push({
      timestamp: closedTime,
      position: entry.direction === 'BUY' ? 'aboveBar' : 'belowBar',
      shape: 'circle',
      color: '#f59e0b',
      text: 'End',
    })
  }
  return markers
}

function buildAnalysisMarkers(records: AnalysisRecord[], candles: CandleBar[]): ForexChartMarker[] {
  const markers: Array<ForexChartMarker | null> = records
    .map(record => {
      const timestamp = findMarkerTimestamp(candles, record.decided_at, null)
      if (!timestamp) return null
      const decision = String(record.decision ?? '').toUpperCase()
      const label = decision === 'BIAS_LONG' ? 'U' : decision === 'BIAS_SHORT' ? 'D' : 'N'
      return {
        timestamp,
        position: 'inBar',
        shape: 'square',
        color: '#fb923c',
        text: label,
        payload: record,
      } satisfies ForexChartMarker
    })
  return markers.filter((marker): marker is ForexChartMarker => marker !== null)
}

export function Orderbook() {
  const [entries, setEntries] = useState<OrderbookEntrySummary[]>([])
  const entriesRef = useRef<OrderbookEntrySummary[]>([])
  // Keep ref in sync so refreshEntries callback always sees latest entries
  const setEntriesWithRef = (data: OrderbookEntrySummary[]) => { entriesRef.current = data; setEntries(data) }
  const [selectedId, setSelectedId] = useState<string>('')
  const [selectedEntry, setSelectedEntry] = useState<OrderbookEntryDetail | null>(null)
  const [candles, setCandles] = useState<CandleBar[]>([])
  const [emaFastValues, setEmaFastValues] = useState<IndicatorValue[]>([])
  const [emaSlowValues, setEmaSlowValues] = useState<IndicatorValue[]>([])
  const [rsiValues, setRsiValues] = useState<IndicatorValue[]>([])
  const [atrValues, setAtrValues] = useState<IndicatorValue[]>([])
  const [loading, setLoading] = useState(false)
  const [detailLoading, setDetailLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [kbMsg, setKbMsg] = useState<string | null>(null)
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all')
  const [maxOrders, setMaxOrders] = useState(7)          // applied limit (triggers fetch)
  const [maxOrdersInput, setMaxOrdersInput] = useState('7') // raw input string
  const [chartTimeframe, setChartTimeframe] = useState<ChartTimeframe>('M5')
  const [analysisOpen, setAnalysisOpen] = useState(false)
  const [analysisRecords, setAnalysisRecords] = useState<AnalysisRecord[]>([])
  const [selectedAnalysis, setSelectedAnalysis] = useState<AnalysisRecord | null>(null)
  const [showAnalyses, setShowAnalyses] = useState(true)
  const [tablePercent, setTablePercent] = useState(48)
  const [draggingDivider, setDraggingDivider] = useState(false)
  const splitRootRef = useRef<HTMLDivElement | null>(null)
  const chartRef = useRef<ForexChartHandle | null>(null)

  // Indicator toggles + configurable params
  const [showEma, setShowEma] = useState(false)
  const [emaFastPeriod, setEmaFastPeriod] = useState(20)
  const [emaSlowPeriod, setEmaSlowPeriod] = useState(50)
  const [emaTf, setEmaTf] = useState('H1')
  const dEmaFastPeriod = useDebounce(emaFastPeriod, 400)
  const dEmaSlowPeriod = useDebounce(emaSlowPeriod, 400)
  const dEmaTf = useDebounce(emaTf, 400)
  const [showRsi, setShowRsi] = useState(false)
  const [rsiPeriod, setRsiPeriod] = useState(7)
  const [rsiTf, setRsiTf] = useState('H1')
  const dRsiPeriod = useDebounce(rsiPeriod, 400)
  const dRsiTf = useDebounce(rsiTf, 400)
  const [showAtr, setShowAtr] = useState(false)
  const [atrPeriod, setAtrPeriod] = useState(7)
  const [atrTf, setAtrTf] = useState('H1')
  const dAtrPeriod = useDebounce(atrPeriod, 400)
  const dAtrTf = useDebounce(atrTf, 400)

  const refreshEntries = useCallback(async (forceBrokerSync = false) => {
    setLoading(true)
    setError(null)
    try {
      // Force broker sync for each unique broker+pair before reading local DB
      // Use ref to avoid stale closure over entries state
      const currentEntries = entriesRef.current
      if (forceBrokerSync && currentEntries.length > 0) {
        const seen = new Set<string>()
        const syncs = currentEntries
          .filter(e => e.broker_name && e.pair)
          .filter(e => {
            const key = `${e.broker_name}:${e.pair}`
            if (seen.has(key)) return false
            seen.add(key); return true
          })
          .map(e => api.executeTool('trigger_sync', {}, e.agent_id, e.broker_name, null, e.pair).catch(() => null))
        await Promise.all(syncs)
      }
      const data = await api.getOrderbookEntries({ status_filter: statusFilter, limit: maxOrders })
      setEntriesWithRef(data)
      setSelectedId(prev => (prev && data.some(entry => entry.id === prev) ? prev : (data[0]?.id ?? '')))
    } catch (err) {
      setError(String(err))
    } finally {
      setLoading(false)
    }
  }, [statusFilter, maxOrders])

  useEffect(() => {
    void refreshEntries()
  }, [refreshEntries])

  useEffect(() => {
    if (!selectedId) {
      setSelectedEntry(null)
      setCandles([])
      return
    }
    let cancelled = false
    async function loadDetail() {
      setDetailLoading(true)
      try {
        const [detail, chartCandles] = await Promise.all([
          api.getOrderbookEntry(selectedId),
          api.getOrderbookCandles(selectedId, chartTimeframe, 2000),
        ])
        if (cancelled) return
        setSelectedEntry(detail)
        setCandles(chartCandles)
      } catch (err) {
        if (!cancelled) setError(String(err))
      } finally {
        if (!cancelled) setDetailLoading(false)
      }
    }
    void loadDetail()
    return () => {
      cancelled = true
    }
  }, [selectedId, chartTimeframe])

  const selectedSummary = useMemo(
    () => entries.find(entry => entry.id === selectedId) ?? null,
    [entries, selectedId],
  )


  useEffect(() => {
    const selectedPair = selectedSummary?.pair ?? null
    if (!showAnalyses || !selectedPair) {
      setAnalysisRecords([])
      return
    }
    let cancelled = false
    async function loadAnalyses() {
      try {
        const data = await api.getAnalyses({ pair: selectedPair, limit: 300 })
        if (!cancelled) setAnalysisRecords(data)
      } catch (err) {
        if (!cancelled) setError(String(err))
      }
    }
    void loadAnalyses()
    return () => {
      cancelled = true
    }
  }, [selectedSummary?.pair, showAnalyses])
  const priceLines = useMemo(() => buildPriceLines(selectedEntry), [selectedEntry])
  const markers = useMemo(() => {
    const tradeMarkers = buildMarkers(selectedEntry, candles)
    const analysisMarkers = showAnalyses ? buildAnalysisMarkers(analysisRecords, candles) : []
    return [...tradeMarkers, ...analysisMarkers]
  }, [selectedEntry, candles, showAnalyses, analysisRecords])

  useEffect(() => {
    if (!showEma || !selectedEntry) { setEmaFastValues([]); setEmaSlowValues([]); return }
    const history = Math.min(500, candles.length + Math.max(dEmaFastPeriod, dEmaSlowPeriod))
    Promise.all([
      api.calculateIndicator({ indicator: 'EMA', period: dEmaFastPeriod, timeframe: dEmaTf, history, pair: selectedEntry.pair, broker_name: selectedEntry.broker_name }),
      api.calculateIndicator({ indicator: 'EMA', period: dEmaSlowPeriod, timeframe: dEmaTf, history, pair: selectedEntry.pair, broker_name: selectedEntry.broker_name }),
    ]).then(([fast, slow]) => { setEmaFastValues(fast.values ?? []); setEmaSlowValues(slow.values ?? []) })
      .catch(() => { setEmaFastValues([]); setEmaSlowValues([]) })
  }, [showEma, selectedEntry, dEmaFastPeriod, dEmaSlowPeriod, dEmaTf, candles.length])

  useEffect(() => {
    if (!showRsi || !selectedEntry) { setRsiValues([]); return }
    api.calculateIndicator({ indicator: 'RSI', period: dRsiPeriod, timeframe: dRsiTf, history: Math.min(500, candles.length + dRsiPeriod), pair: selectedEntry.pair, broker_name: selectedEntry.broker_name })
      .then(r => setRsiValues(r.values ?? []))
      .catch(() => setRsiValues([]))
  }, [showRsi, selectedEntry, dRsiPeriod, dRsiTf, candles.length])

  useEffect(() => {
    if (!showAtr || !selectedEntry) { setAtrValues([]); return }
    api.calculateIndicator({ indicator: 'ATR', period: dAtrPeriod, timeframe: dAtrTf, history: Math.min(500, candles.length + dAtrPeriod), pair: selectedEntry.pair, broker_name: selectedEntry.broker_name })
      .then(r => setAtrValues(r.values ?? []))
      .catch(() => setAtrValues([]))
  }, [showAtr, selectedEntry, dAtrPeriod, dAtrTf, candles.length])

  const overlayLines: ForexChartOverlayLine[] = showEma ? [
    { key: 'ema_fast', label: `EMA ${emaFastPeriod}`, color: '#facc15', values: emaFastValues },
    { key: 'ema_slow', label: `EMA ${emaSlowPeriod}`, color: '#60a5fa', values: emaSlowValues },
  ] : []
  const oscillators: ForexChartOscillator[] = [
    ...(showRsi ? [{ key: 'rsi_primary', label: `RSI ${rsiPeriod}`, color: '#a78bfa', precision: 1, values: rsiValues }] : []),
    ...(showAtr ? [{ key: 'atr_primary', label: `ATR ${atrPeriod}`, color: '#94a3b8', precision: 5, values: atrValues }] : []),
  ]

  const inputCls = 'w-10 bg-gray-800 border border-gray-600 rounded px-1 text-gray-200 text-xs text-center'
  const selectCls = 'bg-gray-800 border border-gray-600 rounded px-1 text-gray-200 text-xs'
  const tfOpts = Object.keys(TF_MINUTES)
  const indicatorControls = selectedEntry ? (
    <>
      <span className="flex items-center gap-1.5">
        <label className="flex items-center gap-1 cursor-pointer select-none">
          <input type="checkbox" checked={showEma} onChange={e => setShowEma(e.target.checked)} className="accent-yellow-400" />
          <span className={showEma ? 'text-yellow-400' : ''}>EMA</span>
        </label>
        <span className="inline-block w-2 h-2 rounded-full bg-yellow-400 shrink-0" title="Fast EMA" />
        <input type="number" min={1} max={500} value={emaFastPeriod} onChange={e => setEmaFastPeriod(Math.max(1, Number(e.target.value)))} className={inputCls} title="Fast period" />
        <span className="inline-block w-2 h-2 rounded-full bg-sky-400 shrink-0" title="Slow EMA" />
        <input type="number" min={1} max={500} value={emaSlowPeriod} onChange={e => setEmaSlowPeriod(Math.max(1, Number(e.target.value)))} className={inputCls} title="Slow period" />
        <select value={emaTf} onChange={e => setEmaTf(e.target.value)} className={selectCls}>
          {tfOpts.map(tf => <option key={tf}>{tf}</option>)}
        </select>
      </span>
      <span className="flex items-center gap-1.5">
        <label className="flex items-center gap-1 cursor-pointer select-none">
          <input type="checkbox" checked={showRsi} onChange={e => setShowRsi(e.target.checked)} className="accent-violet-400" />
          <span className={showRsi ? 'text-violet-400' : ''}>RSI</span>
        </label>
        <input type="number" min={1} max={500} value={rsiPeriod} onChange={e => setRsiPeriod(Math.max(1, Number(e.target.value)))} className={inputCls} title="Period" />
        <select value={rsiTf} onChange={e => setRsiTf(e.target.value)} className={selectCls}>
          {tfOpts.map(tf => <option key={tf}>{tf}</option>)}
        </select>
      </span>
      <span className="flex items-center gap-1.5">
        <label className="flex items-center gap-1 cursor-pointer select-none">
          <input type="checkbox" checked={showAtr} onChange={e => setShowAtr(e.target.checked)} className="accent-slate-400" />
          <span className={showAtr ? 'text-slate-300' : ''}>ATR</span>
        </label>
        <input type="number" min={1} max={500} value={atrPeriod} onChange={e => setAtrPeriod(Math.max(1, Number(e.target.value)))} className={inputCls} title="Period" />
        <select value={atrTf} onChange={e => setAtrTf(e.target.value)} className={selectCls}>
          {tfOpts.map(tf => <option key={tf}>{tf}</option>)}
        </select>
      </span>
    </>
  ) : null

  const timeframeControls = useMemo(
    () => (
      <>
        <label className="inline-flex items-center gap-1 text-xs text-gray-400 mr-2">
          <input
            type="checkbox"
            checked={showAnalyses}
            onChange={e => setShowAnalyses(e.target.checked)}
            className="rounded border-gray-600 bg-gray-900 text-emerald-500"
          />
          Show the Analyses
        </label>
        {(['M5', 'M15', 'M30', 'H1'] as ChartTimeframe[]).map(tf => (
          <button
            key={tf}
            onClick={() => setChartTimeframe(tf)}
            className={[
              'px-2 py-0.5 rounded border text-xs',
              chartTimeframe === tf
                ? 'border-emerald-500 bg-emerald-900/30 text-emerald-300'
                : 'border-gray-700 bg-gray-900 text-gray-400 hover:text-gray-200',
            ].join(' ')}
          >
            {tf}
          </button>
        ))}
      </>
    ),
    [chartTimeframe, showAnalyses],
  )
  const tableBasis = `${tablePercent}%`
  const chartBasis = `${100 - tablePercent}%`

  useEffect(() => {
    if (!draggingDivider) return
    const root = splitRootRef.current
    if (!root) return

    const onPointerMove = (event: PointerEvent) => {
      const rect = root.getBoundingClientRect()
      const relative = ((event.clientY - rect.top) / rect.height) * 100
      const bounded = Math.max(28, Math.min(72, relative))
      setTablePercent(bounded)
    }
    const onPointerUp = () => setDraggingDivider(false)

    window.addEventListener('pointermove', onPointerMove)
    window.addEventListener('pointerup', onPointerUp)
    document.body.style.userSelect = 'none'
    document.body.style.cursor = 'row-resize'
    return () => {
      window.removeEventListener('pointermove', onPointerMove)
      window.removeEventListener('pointerup', onPointerUp)
      document.body.style.userSelect = ''
      document.body.style.cursor = ''
    }
  }, [draggingDivider])

  const handlePrint = useCallback(() => {
    if (!selectedEntry) return
    const chartImage = chartRef.current?.captureImage() ?? null
    const printWindow = window.open('', '_blank', 'width=1200,height=900')
    if (!printWindow) {
      setError('Unable to open print preview window.')
      return
    }
    const indicators = (selectedEntry.analysis_overlays?.indicators ?? [])
      .map(indicator => `<span class="pill">${indicator.name} ${indicator.value}</span>`)
      .join('')
    const supports = (selectedEntry.analysis_overlays?.levels?.support ?? []).map(formatPrice).join(', ') || '-'
    const resistances = (selectedEntry.analysis_overlays?.levels?.resistance ?? []).map(formatPrice).join(', ') || '-'
    const html = `<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <title>Trade Report ${selectedEntry.pair}</title>
    <style>
      body { font-family: Arial, sans-serif; color: #111827; margin: 24px; }
      h1, h2 { margin: 0 0 10px; }
      .meta { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; margin: 16px 0; }
      .card { border: 1px solid #d1d5db; border-radius: 10px; padding: 12px; }
      .row { display: grid; grid-template-columns: 120px 1fr; gap: 8px; margin: 4px 0; }
      .label { color: #6b7280; font-size: 12px; text-transform: uppercase; }
      .value { color: #111827; font-size: 14px; }
      .pill { display: inline-block; padding: 2px 8px; margin: 2px 6px 2px 0; border: 1px solid #cbd5e1; border-radius: 999px; font-size: 12px; }
      .chart { margin: 18px 0; }
      .chart img { width: 100%; border: 1px solid #d1d5db; border-radius: 12px; }
      pre { white-space: pre-wrap; word-break: break-word; background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 10px; padding: 12px; font-size: 12px; line-height: 1.5; }
      @media print { body { margin: 12px; } }
    </style>
  </head>
  <body>
    <h1>Trade Report</h1>
    <div class="value">${selectedEntry.pair} · ${selectedEntry.direction} · ${selectedEntry.status}</div>
    <div class="meta">
      <div class="card">
        <h2>Timing</h2>
        <div class="row"><div class="label">From</div><div class="value">${formatTs(getTradeStartAt(selectedEntry))}</div></div>
        <div class="row"><div class="label">To</div><div class="value">${formatTs(getTradeEndDisplay(selectedEntry))}</div></div>
        <div class="row"><div class="label">Close</div><div class="value">${getCloseDisplay(selectedEntry)}</div></div>
      </div>
      <div class="card">
        <h2>Execution</h2>
        <div class="row"><div class="label">Entry</div><div class="value">${formatPrice(selectedEntry.fill_price ?? selectedEntry.requested_price)}</div></div>
        <div class="row"><div class="label">Exit</div><div class="value">${formatPrice(selectedEntry.close_price)}</div></div>
        <div class="row"><div class="label">SL / TP</div><div class="value">${formatPrice(selectedEntry.stop_loss)} / ${formatPrice(selectedEntry.take_profit)}</div></div>
        <div class="row"><div class="label">Units</div><div class="value">${selectedEntry.units.toLocaleString()}</div></div>
      </div>
      <div class="card">
        <h2>Result</h2>
        <div class="row"><div class="label">Stake</div><div class="value">${formatMoney(selectedEntry.stake_estimate)}</div></div>
        <div class="row"><div class="label">PnL</div><div class="value">${formatMoney(selectedEntry.pnl_account_currency)}</div></div>
        <div class="row"><div class="label">Decision</div><div class="value">${selectedEntry.decision_context?.decision ?? '-'}</div></div>
        <div class="row"><div class="label">Confidence</div><div class="value">${selectedEntry.signal_confidence.toFixed(2)}</div></div>
      </div>
    </div>
    <div class="card">
      <h2>AA Context</h2>
      <div class="row"><div class="label">Indicators</div><div class="value">${indicators || 'None'}</div></div>
      <div class="row"><div class="label">Support</div><div class="value">${supports}</div></div>
      <div class="row"><div class="label">Resistance</div><div class="value">${resistances}</div></div>
    </div>
    ${chartImage ? `<div class="chart"><h2>Chart</h2><img src="${chartImage}" alt="Trade chart" /></div>` : ''}
    <div style="page-break-before:always">
      <h2>AA Analysis</h2>
      <pre>${(selectedEntry.analysis_text || 'No stored analysis.').replace(/</g, '&lt;').replace(/>/g, '&gt;')}</pre>
    </div>
    <script>
      window.onload = () => {
        window.print();
      };
    </script>
  </body>
</html>`
    printWindow.document.open()
    printWindow.document.write(html)
    printWindow.document.close()
  }, [selectedEntry])

  const formatAnalysisAsMarkdown = useCallback((entry: typeof selectedEntry) => {
    if (!entry) return 'No stored analysis.'
    const rec = (entry.market_context_snapshot as Record<string, unknown>)?.analyst_recommendation as Record<string, unknown> | undefined
    if (!rec) return entry.analysis_text || 'No stored analysis.'

    const flags = Array.isArray(rec.conflict_flags) && rec.conflict_flags.length
      ? (rec.conflict_flags as string[]).join(', ')
      : '–'

    const table = `| | |
|---|---|
| Decision | ${rec.decision ?? '–'} |
| Signal | ${rec.order_start_signal ?? '–'} |
| Quality | ${rec.order_start_quality ?? '–'} |
| Setup | ${rec.setup_type ?? '–'} |
| Aggressiveness | ${rec.strategy_aggressiveness ?? '–'} |
| Invalidation | ${rec.invalidation_level ?? '–'} |
| First Target | ${rec.first_target ?? '–'} |
| Conflict Flags | ${flags} |`

    const sections = [
      ['Summary',            rec.analysis_summary],
      ['Entry Reason',       rec.order_start_reason],
      ['Trend',              rec.trend_assessment],
      ['Momentum',           rec.momentum_assessment],
      ['Volatility',         rec.volatility_assessment],
      ['Support/Resistance', rec.support_resistance_assessment],
      ['M5 Price Action',    rec.m5_price_action_assessment],
      ['Entry Quality',      rec.entry_quality_reason],
    ]
      .filter(([, v]) => v)
      .map(([label, v]) => `**${label}:** ${v}`)
      .join('\n\n')

    return `${table}\n\n${sections}`
  }, [])

  const handleKbImport = useCallback(async () => {
    if (!selectedEntry) return
    const chartImage = chartRef.current?.captureImage() ?? null
    const indicators = (selectedEntry.analysis_overlays?.indicators ?? [])
      .map(i => `- ${i.name}: ${i.value}`).join('\n') || '- –'
    const supports = (selectedEntry.analysis_overlays?.levels?.support ?? []).map(formatPrice).join(', ') || '–'
    const resistances = (selectedEntry.analysis_overlays?.levels?.resistance ?? []).map(formatPrice).join(', ') || '–'

    const md = `# Trade Report — ${selectedEntry.pair} ${selectedEntry.direction}

**Status:** ${selectedEntry.status} · **Direction:** ${selectedEntry.direction}
${chartImage ? `\n## Chart\n<img src="${chartImage}" style="width:100%" />\n` : ''}
## Result
| | |
|---|---|
| Stake | ${formatMoney(selectedEntry.stake_estimate)} |
| PnL | ${formatMoney(selectedEntry.pnl_account_currency)} |
| Decision | ${selectedEntry.decision_context?.decision ?? '–'} |
| Confidence | ${selectedEntry.signal_confidence.toFixed(2)} |

## Timing
| | |
|---|---|
| From | ${formatTs(getTradeStartAt(selectedEntry))} |
| To | ${formatTs(getTradeEndDisplay(selectedEntry))} |
| Close | ${getCloseDisplay(selectedEntry)} |

## Execution
| | |
|---|---|
| Entry | ${formatPrice(selectedEntry.fill_price ?? selectedEntry.requested_price)} |
| Exit | ${formatPrice(selectedEntry.close_price)} |
| SL / TP | ${formatPrice(selectedEntry.stop_loss)} / ${formatPrice(selectedEntry.take_profit)} |
| Units | ${selectedEntry.units.toLocaleString()} |

## AA Context
**Indicators:**
${indicators}

**Support:** ${supports}
**Resistance:** ${resistances}

## AA Analysis

${formatAnalysisAsMarkdown(selectedEntry)}
`
    try {
      await kbImport('Orderbook', md)
      setKbMsg('✓ In Knowledgebase gespeichert')
      setTimeout(() => setKbMsg(null), 2000)
    } catch (e) {
      setError(`KB Import failed: ${String(e)}`)
    }
  }, [selectedEntry])

  return (
    <div className="h-full flex flex-col bg-gray-950 text-gray-100">
      <div className="px-6 py-4 border-b border-gray-800 flex items-center justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold">Orderbook</h2>
          <p className="text-sm text-gray-400">Top half table, bottom half chart with entry, exit, and analysis lines.</p>
        </div>
        <div className="flex items-center gap-2">
          {(['all', 'open', 'closed', 'rejected'] as StatusFilter[]).map(filter => (
            <button
              key={filter}
              onClick={() => setStatusFilter(filter)}
              className={[
                'px-3 py-1 rounded border text-sm',
                statusFilter === filter
                  ? 'border-emerald-500 bg-emerald-900/30 text-emerald-300'
                  : 'border-gray-700 bg-gray-900 text-gray-400 hover:text-gray-200',
              ].join(' ')}
            >
              {filter}
            </button>
          ))}
          <label className="flex items-center gap-1 text-xs text-gray-400">
            Max
            <input
              type="number"
              min={1}
              step={1}
              value={maxOrdersInput}
              onChange={e => setMaxOrdersInput(e.target.value)}
              onBlur={() => {
                const v = Math.max(1, Math.trunc(Number(maxOrdersInput) || 1))
                setMaxOrdersInput(String(v))
                setMaxOrders(v)
              }}
              onKeyDown={e => {
                if (e.key === 'Enter') (e.target as HTMLInputElement).blur()
              }}
              className="w-14 bg-gray-800 border border-gray-700 rounded px-2 py-1 text-sm text-gray-200 text-right"
              title="Maximum number of orders to fetch and display. Confirm with Enter or Tab."
            />
          </label>
          <button
            onClick={() => void refreshEntries(true)}
            className="px-3 py-1 rounded border border-gray-700 bg-gray-900 text-gray-300 hover:text-white flex items-center gap-2 text-sm"
          >
            <RefreshCcw className={loading ? 'w-4 h-4 animate-spin' : 'w-4 h-4'} />
            Refresh
          </button>
          <button
            onClick={handlePrint}
            disabled={!selectedEntry}
            className="px-3 py-1 rounded border border-gray-700 bg-gray-900 text-gray-300 hover:text-white disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-2 text-sm"
          >
            <Printer className="w-4 h-4" />
            Print
          </button>
          <button
            onClick={() => void handleKbImport()}
            disabled={!selectedEntry}
            className="px-3 py-1 rounded border border-gray-700 bg-gray-900 text-gray-300 hover:text-white disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-2 text-sm"
            title="In Knowledgebase [Import] speichern"
          >
            <BookOpen className="w-4 h-4" />
            → KB
          </button>
          {kbMsg && <span className="text-xs text-emerald-400">{kbMsg}</span>}
        </div>
      </div>

      {error && <div className="px-6 py-2 text-sm text-red-400 border-b border-red-900/40">{error}</div>}

      <div ref={splitRootRef} className="flex-1 min-h-0 flex flex-col">
        <section className="min-h-0 overflow-hidden" style={{ flexBasis: tableBasis }}>
          <div className="h-full overflow-auto">
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-gray-950/95 backdrop-blur border-b border-gray-800 text-gray-400">
                <tr>
                  <th className="px-3 py-2 text-left">Pair</th>
                  <th className="px-3 py-2 text-left">From</th>
                  <th className="px-3 py-2 text-left">To</th>
                  <th className="px-3 py-2 text-right">HH:MM</th>
                  <th className="px-3 py-2 text-left">Id</th>
                  <th className="px-3 py-2 text-right">Units</th>
                  <th className="px-3 py-2 text-right">Stake</th>
                  <th className="px-3 py-2 text-right">Result</th>
                  <th className="px-3 py-2 text-left">Close</th>
                  <th className="px-3 py-2 text-left">Analysis</th>
                </tr>
              </thead>
              <tbody>
                {entries.map(entry => (
                  <tr
                    key={entry.id}
                    onClick={() => setSelectedId(entry.id)}
                    className={[
                      'border-b border-gray-900 cursor-pointer hover:bg-gray-900/60',
                      selectedId === entry.id ? 'bg-emerald-900/20' : '',
                    ].join(' ')}
                  >
                    <td className="px-3 py-2">
                      <div className="flex items-center gap-2">
                        <div className="font-medium text-gray-100">{entry.pair}</div>
                        {!entry.confirmed_by_broker && (
                          <span title="Broker confirmation pending" className="text-amber-400">
                            <AlertCircle className="w-3.5 h-3.5" />
                          </span>
                        )}
                      </div>
                      <div className="text-xs text-gray-500">{entry.direction} · {entry.status}</div>
                    </td>
                    <td className={[
                      'px-3 py-2',
                      isTradeStartProvisional(entry) ? 'text-amber-300' : 'text-gray-300',
                    ].join(' ')}>
                      {formatTs(getTradeStartAt(entry))}
                    </td>
                    <td className={[
                      'px-3 py-2',
                      isTradeEndProvisional(entry) ? 'text-amber-300' : 'text-gray-300',
                    ].join(' ')}>
                      {formatTs(getTradeEndDisplay(entry))}
                    </td>
                    <td className="px-3 py-2 text-right text-gray-400 tabular-nums">{tradeDuration(entry)}</td>
                    <td className="px-3 py-2 text-gray-400 text-xs font-mono">{entry.broker_order_id ?? '-'}</td>
                    <td className="px-3 py-2 text-right text-gray-200">{entry.units.toLocaleString()}</td>
                    <td className="px-3 py-2 text-right text-gray-200">{formatStake(entry.stake_estimate)}</td>
                    <td className={[
                      'px-3 py-2 text-right',
                      (entry.pnl_account_currency ?? 0) >= 0 ? 'text-emerald-300' : 'text-red-300',
                    ].join(' ')}>
                      {formatResult(entry.pnl_account_currency)}
                    </td>
                    <td className="px-3 py-2 text-gray-300">
                      <div>{getCloseDisplay(entry)}</div>
                      <div className="text-xs text-gray-500 truncate max-w-[260px]">
                        {entry.close_reasoning || entry.status}
                      </div>
                    </td>
                    <td className="px-3 py-2">
                      <button
                        onClick={event => {
                          event.stopPropagation()
                          setSelectedId(entry.id)
                          setAnalysisOpen(true)
                        }}
                        className="inline-flex items-center gap-2 px-2 py-1 rounded border border-gray-700 bg-gray-900 text-gray-300 hover:text-white text-xs"
                      >
                        <FileText className="w-3.5 h-3.5" />
                        Open
                      </button>
                    </td>
                  </tr>
                ))}
                {!loading && entries.length === 0 && (
                  <tr>
                    <td colSpan={8} className="px-3 py-8 text-center text-gray-500">
                      No orders in the orderbook.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </section>

        <div
          onPointerDown={() => setDraggingDivider(true)}
          className="h-3 shrink-0 bg-gray-950 border-y border-gray-800 cursor-row-resize flex items-center justify-center"
          title="Drag to resize table and chart"
        >
          <div className="w-16 h-1 rounded-full bg-gray-700" />
        </div>

        <section className="min-h-0 px-6 py-4 flex flex-col gap-4 overflow-hidden" style={{ flexBasis: chartBasis }}>
          <div className="flex items-center gap-3 text-[11px]">
            <div className="shrink-0 mr-1">
              <div className="text-sm font-semibold text-gray-100 leading-tight">
                {selectedSummary ? `${selectedSummary.pair} · ${selectedSummary.direction}` : 'Select an order'}
              </div>
              <div className="text-[11px] text-gray-400 leading-tight mt-0.5">
                {selectedEntry?.decision_context?.decision ?? '-'} · {selectedEntry?.signal_confidence?.toFixed(2) ?? '-'} · {selectedEntry?.decision_context?.setup_type ?? '-'}
              </div>
            </div>
            <div className="rounded-lg border border-gray-800 bg-gray-900/40 px-2 py-1 shrink-0">
              <div className="grid grid-cols-2 gap-x-3 gap-y-0.5">
                <span className="text-gray-500">Entry</span>
                <span className="text-gray-200 text-right">{formatPrice(selectedEntry?.fill_price ?? selectedEntry?.requested_price)}</span>
                <span className="text-gray-500">Exit</span>
                <span className="text-gray-200 text-right">{formatPrice(selectedEntry?.close_price)}</span>
              </div>
            </div>
            <div className="rounded-lg border border-gray-800 bg-gray-900/40 px-2 py-1 shrink-0">
              <div className="grid grid-cols-2 gap-x-3 gap-y-0.5">
                <span className="text-gray-500">SL</span>
                <span className="text-gray-200 text-right">{formatPrice(selectedEntry?.stop_loss)}</span>
                <span className="text-gray-500">TP</span>
                <span className="text-gray-200 text-right">{formatPrice(selectedEntry?.take_profit)}</span>
              </div>
            </div>
            <div className="rounded-lg border border-gray-800 bg-gray-900/40 px-2 py-1 min-w-0">
              <div className="grid grid-cols-[auto_1fr] gap-x-2 gap-y-0.5">
                <span className="text-gray-500 shrink-0">Support</span>
                <span className="text-gray-200 truncate">{(selectedEntry?.analysis_overlays?.levels?.support ?? []).map(formatPrice).join(', ') || '-'}</span>
                <span className="text-gray-500 shrink-0">Resistance</span>
                <span className="text-gray-200 truncate">{(selectedEntry?.analysis_overlays?.levels?.resistance ?? []).map(formatPrice).join(', ') || '-'}</span>
              </div>
            </div>
            <div className="rounded-lg border border-gray-800 bg-gray-900/40 px-2 py-1 shrink-0">
              <div className="flex flex-wrap gap-1">
                {(selectedEntry?.analysis_overlays?.indicators ?? []).map(indicator => (
                  <span
                    key={`${indicator.name}-${indicator.timeframe}`}
                    className="px-1 py-0.5 rounded bg-gray-800 text-gray-200"
                  >
                    {indicator.name} {indicator.value}
                  </span>
                ))}
                {(selectedEntry?.analysis_overlays?.indicators ?? []).length === 0 && (
                  <span className="text-gray-500">—</span>
                )}
              </div>
            </div>
          </div>

          <div className="flex-1 min-h-0 rounded-xl border border-gray-800 bg-gray-900/40 p-3">
            {detailLoading ? (
              <div className="h-full flex items-center justify-center text-gray-500">Loading chart...</div>
            ) : selectedEntry && candles.length > 0 ? (
              <ForexChart
                ref={chartRef}
                candles={candles}
                priceLines={priceLines}
                markers={markers}
                overlayLines={overlayLines}
                oscillators={oscillators}
                ranges={[50, 100, 200, 400]}
                initialRange={100}
                controls={timeframeControls}
                indicatorControls={indicatorControls}
                onMarkerSelect={marker => {
                  if (marker.payload) {
                    setSelectedAnalysis(marker.payload as AnalysisRecord)
                  }
                }}
              />
            ) : (
              <div className="h-full flex items-center justify-center text-gray-500">
                No chart data for the selected order.
              </div>
            )}
          </div>
        </section>
      </div>

      {analysisOpen && selectedEntry && (
        <div className="fixed inset-0 z-50 bg-black/70 flex items-center justify-center p-6">
          <div className="w-full max-w-5xl max-h-[85vh] bg-gray-950 border border-gray-700 rounded-xl overflow-hidden flex flex-col">
            <div className="px-5 py-4 border-b border-gray-800 flex items-center justify-between">
              <div>
                <h3 className="text-base font-semibold text-gray-100">AA Analysis</h3>
                <p className="text-sm text-gray-400">{selectedEntry.pair} · {selectedEntry.decision_context?.decision ?? '-'}</p>
              </div>
              <div className="flex items-center gap-2">
                <CopyButton getText={() => selectedEntry.analysis_text || ''} />
                <button
                  onClick={() => setAnalysisOpen(false)}
                  className="px-3 py-1 rounded border border-gray-700 bg-gray-900 text-gray-300 hover:text-white text-sm"
                >
                  Close
                </button>
              </div>
            </div>
            <div className="flex-1 overflow-auto p-5">
              <pre className="whitespace-pre-wrap break-words text-sm text-gray-200 leading-6">
                {selectedEntry.analysis_text || 'No stored analysis.'}
              </pre>
            </div>
          </div>
        </div>
      )}

      {selectedAnalysis && (
        <div className="fixed inset-0 z-50 bg-black/70 flex items-center justify-center p-6">
          <div className="w-full max-w-5xl max-h-[85vh] bg-gray-950 border border-gray-700 rounded-xl overflow-hidden flex flex-col">
            <div className="px-5 py-4 border-b border-gray-800 flex items-center justify-between">
              <div>
                <h3 className="text-base font-semibold text-gray-100">AA Recommendation</h3>
                <p className="text-sm text-gray-400">
                  {selectedAnalysis.pair ?? '-'} · {selectedAnalysis.decision ?? '-'} · {formatTs(selectedAnalysis.decided_at)}
                </p>
              </div>
              <button
                onClick={() => setSelectedAnalysis(null)}
                className="px-3 py-1 rounded border border-gray-700 bg-gray-900 text-gray-300 hover:text-white text-sm"
              >
                Close
              </button>
            </div>
            <div className="flex-1 overflow-auto p-5 space-y-4">
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">
                <div className="rounded border border-gray-800 bg-gray-900/40 p-3">
                  <div className="text-gray-500">Decision</div>
                  <div className="text-gray-100 mt-1">{selectedAnalysis.decision ?? '-'}</div>
                </div>
                <div className="rounded border border-gray-800 bg-gray-900/40 p-3">
                  <div className="text-gray-500">Confidence</div>
                  <div className="text-gray-100 mt-1">
                    {typeof selectedAnalysis.confidence === 'number' ? selectedAnalysis.confidence.toFixed(2) : '-'}
                  </div>
                </div>
                <div className="rounded border border-gray-800 bg-gray-900/40 p-3">
                  <div className="text-gray-500">Order Start</div>
                  <div className="text-gray-100 mt-1">{selectedAnalysis.order_start_signal ?? '-'}</div>
                </div>
                <div className="rounded border border-gray-800 bg-gray-900/40 p-3">
                  <div className="text-gray-500">Entry Quality</div>
                  <div className="text-gray-100 mt-1">{selectedAnalysis.entry_quality ?? '-'}</div>
                </div>
              </div>
              <div className="space-y-1">
                <div className="flex items-center justify-between">
                  <span className="text-xs text-gray-500">Decision JSON</span>
                  <CopyButton getText={() => selectedAnalysis.analysis_text || JSON.stringify(selectedAnalysis.analysis ?? selectedAnalysis.output, null, 2)} />
                </div>
                <pre className="whitespace-pre-wrap break-words text-sm text-gray-200 leading-6">
                  {selectedAnalysis.analysis_text || JSON.stringify(selectedAnalysis.analysis ?? selectedAnalysis.output, null, 2)}
                </pre>
              </div>
              {selectedAnalysis.market_snapshot && (
                <div className="rounded border border-gray-800 bg-gray-900/40 p-4 space-y-3">
                  <div className="flex items-center justify-between">
                    <h4 className="text-sm font-medium text-gray-200">Decision Snapshot</h4>
                    <div className="flex items-center gap-2">
                      <span className="text-xs text-gray-500">
                        {typeof selectedAnalysis.market_snapshot?.snapshot_schema_version === 'string'
                          ? `schema ${String(selectedAnalysis.market_snapshot.snapshot_schema_version)}`
                          : 'no schema'}
                      </span>
                      <CopyButton getText={() => JSON.stringify(selectedAnalysis.market_snapshot, null, 2)} />
                    </div>
                  </div>
                  <pre className="whitespace-pre-wrap break-words text-xs text-gray-300 leading-6">
                    {JSON.stringify(selectedAnalysis.market_snapshot, null, 2)}
                  </pre>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
