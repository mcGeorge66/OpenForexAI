/**
 * PromptWorkbench (APW) — sandbox for testing/tuning an Agent's system prompt
 * against historical candle data, independent of the live trading system.
 *
 * Candle loading + numbering, chart, Analyse-tab indicator overlays (reused
 * Chart-Analysis pattern), Simulation-tab position/step/run mechanics, and
 * the Agent Prompt editor. Chat/Step/Run call `POST /prompt-workbench/chat`,
 * which runs the prompt through a detached (non-registered) `Agent` instance
 * reusing `Agent._run_with_tools` — the same LLM/tool-use loop real agents
 * use, not a second implementation. The agent has `calculate_indicator` plus
 * two sandbox-only tools, `zone_marker` and `trade_marker`, which the backend
 * echoes back as structured `annotations` — rendered here as chart drawings
 * (reusing the existing rect/trendline DrawingManager primitives, not a new
 * chart feature) and accumulated client-side across turns, since the backend
 * keeps no session state. The real tool_blocks/calculation_blocks Simulation
 * pipeline (mini Snapshot Designer) is not built yet.
 *
 * Position semantics (as specified): candles count down from `total`
 * (oldest, at the edge of the loaded window) to `0` (newest / fully
 * revealed). The agent's visible window is always candles `total`..`position`.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Play, RefreshCcw, Square, StepForward } from 'lucide-react'
import { LineStyle, type UTCTimestamp } from 'lightweight-charts'
import {
  api,
  type CandleBar,
  type InitialConsoleModuleItem,
  type PromptWorkbenchAnnotation,
  type PromptWorkbenchTradeAnnotation,
  type PromptWorkbenchZoneAnnotation,
} from '@/api/client'
import {
  ForexChart,
  type ForexChartHandle,
  type ForexChartMarker,
  type ForexChartOscillator,
  type ForexChartOverlayLine,
} from '@/components/charts/ForexChart'
import type { Drawing } from '@/components/charts/drawing/types'
import {
  IndicatorsPanel,
  INDICATOR_DEFS,
  DEFAULT_COLORS,
  type IndicatorInstance,
  type IndicatorName,
} from '@/components/charts/IndicatorsPanel'
import { PlainTextMonacoEditor } from '@/components/common/PlainTextMonacoEditor'
import { TF_MINUTES } from '@/utils/indicators'

function toUnixTime(iso: string): UTCTimestamp {
  return Math.floor(new Date(iso).getTime() / 1000) as UTCTimestamp
}

function pipSize(price: number): number {
  return price > 20 ? 0.01 : 0.0001
}

const TIMEFRAMES = Object.keys(TF_MINUTES).filter(tf => tf !== 'M1')

type ToolTab = 'analyse' | 'simulation'

interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  timestamp: string
}

function now(): string {
  return new Date().toISOString().replace('T', ' ').substring(11, 19) + ' UTC'
}

function sleep(ms: number): Promise<void> {
  return new Promise(resolve => setTimeout(resolve, ms))
}

export function PromptWorkbench() {
  // ── Workbench config save/load — placeholders, wired up in a later step ──
  const [savedConfigName, setSavedConfigName] = useState('')

  // ── Candle storage / loading ────────────────────────────────────────────
  const [systemConfig, setSystemConfig] = useState<Record<string, unknown> | null>(null)
  const [brokers, setBrokers] = useState<InitialConsoleModuleItem[]>([])
  const [brokerName, setBrokerName] = useState<string | null>(null)
  const [pair, setPair] = useState('')
  const [timeframe, setTimeframe] = useState('M5')
  const [candleCount, setCandleCount] = useState(500)
  const [candles, setCandles] = useState<CandleBar[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const chartRef = useRef<ForexChartHandle | null>(null)

  // ── Draggable divider between the chart and the bottom 3-column area ────
  const [chartHeight, setChartHeight] = useState(260)
  const resizingRef = useRef(false)
  const resizeStartYRef = useRef(0)
  const resizeStartHeightRef = useRef(0)

  useEffect(() => {
    function onMouseMove(e: MouseEvent) {
      if (!resizingRef.current) return
      const delta = e.clientY - resizeStartYRef.current
      setChartHeight(Math.max(160, Math.min(800, resizeStartHeightRef.current + delta)))
    }
    function onMouseUp() { resizingRef.current = false }
    window.addEventListener('mousemove', onMouseMove)
    window.addEventListener('mouseup', onMouseUp)
    return () => {
      window.removeEventListener('mousemove', onMouseMove)
      window.removeEventListener('mouseup', onMouseUp)
    }
  }, [])

  const availablePairs = useMemo(() => {
    const agentsCfg = (systemConfig?.agents ?? {}) as Record<string, Record<string, unknown>>
    const pairs = new Set<string>()
    for (const cfg of Object.values(agentsCfg)) {
      if (cfg.pair) pairs.add(String(cfg.pair).toUpperCase())
    }
    return [...pairs].sort()
  }, [systemConfig])

  const agentPromptOptions = useMemo(() => {
    const agentsCfg = (systemConfig?.agents ?? {}) as Record<string, Record<string, unknown>>
    return Object.entries(agentsCfg)
      .filter(([, cfg]) => typeof cfg.system_prompt === 'string' && cfg.system_prompt.trim())
      .map(([agentId, cfg]) => ({
        agentId,
        systemPrompt: String(cfg.system_prompt),
        llm: typeof cfg.llm === 'string' ? cfg.llm : '',
      }))
      .sort((a, b) => a.agentId.localeCompare(b.agentId))
  }, [systemConfig])

  const [availableLlmNames, setAvailableLlmNames] = useState<string[]>([])
  useEffect(() => {
    void api.getModuleNames('llm').then(r => setAvailableLlmNames(r.names)).catch(() => setAvailableLlmNames([]))
  }, [])

  useEffect(() => {
    void api.getSystemConfig().then(cfg => setSystemConfig(cfg)).catch(() => setSystemConfig(null))
  }, [])

  useEffect(() => {
    void api.getInitialConsole().then(res => {
      const connected = res.broker.items.filter(b => b.status === 'connected')
      setBrokers(connected)
      setBrokerName(b => b ?? connected[0]?.name ?? null)
    }).catch(() => {})
  }, [])

  useEffect(() => {
    if (!pair && availablePairs.length > 0) setPair(availablePairs[0])
  }, [availablePairs, pair])

  // ── Analyse-tab indicators — same shared panel/types as Chart Analysis ──
  const [indicators, setIndicators] = useState<IndicatorInstance[]>([])
  const indicatorsRef = useRef<IndicatorInstance[]>([])
  useEffect(() => { indicatorsRef.current = indicators }, [indicators])
  const recomputeTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

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

  function addIndicator(name: IndicatorName) {
    const def = INDICATOR_DEFS.find(d => d.name === name)!
    const newInd: IndicatorInstance = {
      id: `ind_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`,
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

  const loadCandles = useCallback(async () => {
    if (!pair) return
    setLoading(true)
    setError(null)
    try {
      const data = await api.getCandles(pair, timeframe, candleCount, brokerName)
      setCandles(data)
      setPosition(0) // fully revealed by default; lower it to set up a simulation start point
      const updated = await recomputeIndicators(data, indicatorsRef.current)
      setIndicators(updated)
      // Fresh candle set — stale zones/trade lines from a previous load no longer apply.
      for (const drawing of chartRef.current?.getDrawings() ?? []) {
        chartRef.current?.removeDrawing(drawing.id)
      }
      renderedDrawingIdsRef.current.clear()
      setAnnotations([])
    } catch (err) {
      setError(String(err))
    } finally {
      setLoading(false)
    }
  }, [pair, timeframe, candleCount, brokerName, recomputeIndicators])

  useEffect(() => { void loadCandles() }, [loadCandles])

  const total = candles.length

  // ── Simulation position (countdown: total=oldest edge .. 0=fully revealed) ─
  const [position, setPosition] = useState(0)
  const [stepSize, setStepSize] = useState(3)
  const [running, setRunning] = useState(false)
  const positionRef = useRef(position)
  const stopRequestedRef = useRef(false)
  useEffect(() => { positionRef.current = position }, [position])

  const visibleCount = total > 0 ? Math.max(0, total - Math.min(position, total)) : 0

  // ── Tools tab ────────────────────────────────────────────────────────────
  const [toolTab, setToolTab] = useState<ToolTab>('analyse')
  const [autoTradeStatus, setAutoTradeStatus] = useState(true)
  const [simPreview, setSimPreview] = useState<string | null>(null)

  const overlayLines: ForexChartOverlayLine[] = useMemo(() => {
    const lines: ForexChartOverlayLine[] = []
    for (const ind of indicators) {
      if (!ind.visible) continue
      if (['RSI', 'ATR', 'SLOPE_E', 'SLOPE_S'].includes(ind.name)) continue
      if (ind.name === 'BB' && ind.bbData) {
        lines.push({ key: `${ind.id}_upper`, label: `BB(${ind.period}) U`, color: ind.color, lineWidth: ind.lineWidth, lineStyle: ind.lineStyle, values: ind.bbData.upper })
        lines.push({ key: `${ind.id}_middle`, label: `BB(${ind.period}) M`, color: ind.color, lineWidth: ind.lineWidth, lineStyle: ind.lineStyle, values: ind.bbData.middle })
        lines.push({ key: `${ind.id}_lower`, label: `BB(${ind.period}) L`, color: ind.color, lineWidth: ind.lineWidth, lineStyle: ind.lineStyle, values: ind.bbData.lower })
      } else {
        lines.push({ key: ind.id, label: `${ind.name}(${ind.period})`, color: ind.color, lineWidth: ind.lineWidth, lineStyle: ind.lineStyle, values: ind.data })
      }
    }
    return lines
  }, [indicators])

  const oscillators: ForexChartOscillator[] = useMemo(() => indicators
    .filter(ind => ind.visible && ['RSI', 'ATR', 'SLOPE_E', 'SLOPE_S'].includes(ind.name))
    .map(ind => ({
      key: ind.id,
      label: ind.name === 'SLOPE_E' ? `SlopeE(${ind.period}) pips/candle`
           : ind.name === 'SLOPE_S' ? `SlopeS(${ind.period}) pips/candle`
           : `${ind.name}(${ind.period})`,
      color: ind.color,
      lineWidth: ind.lineWidth,
      lineStyle: ind.lineStyle,
      precision: ind.name === 'RSI' ? 4 : (['SLOPE_E', 'SLOPE_S'] as string[]).includes(ind.name) ? 4 : 5,
      values: ind.data,
      zeroline: (['SLOPE_E', 'SLOPE_S'] as string[]).includes(ind.name),
    })),
    [indicators],
  )

  const boundaryMarkers: ForexChartMarker[] = useMemo(() => {
    if (toolTab !== 'simulation' || total === 0 || position <= 0 || position >= total) return []
    const boundaryCandle = candles[visibleCount - 1]
    if (!boundaryCandle) return []
    return [{
      timestamp: boundaryCandle.timestamp,
      position: 'aboveBar',
      shape: 'arrowDown',
      color: '#f59e0b',
      text: `Agent-Grenze\n#${position}`,
    }]
  }, [toolTab, total, position, visibleCount, candles])

  // ── Agent-drawn annotations (zone_marker / trade_marker) ─────────────────
  // Accumulated client-side across turns — the backend keeps no session state,
  // each response only returns the annotations created during that one call.
  const [annotations, setAnnotations] = useState<PromptWorkbenchAnnotation[]>([])
  const renderedDrawingIdsRef = useRef<Set<string>>(new Set())

  const openTrades = useMemo(() => {
    const open = new Map<string, PromptWorkbenchTradeAnnotation>()
    for (const a of annotations) {
      if (a.kind !== 'trade') continue
      if (a.action === 'open') open.set(a.trade_id, a)
      else open.delete(a.trade_id)
    }
    return open
  }, [annotations])

  const tradeMarkers: ForexChartMarker[] = useMemo(() => annotations
    .filter((a): a is PromptWorkbenchTradeAnnotation => a.kind === 'trade')
    .map(a => ({
      timestamp: a.timestamp,
      position: a.action === 'open' ? 'belowBar' : 'aboveBar',
      shape: a.action === 'open' ? (a.direction === 'short' ? 'arrowDown' : 'arrowUp') : 'circle',
      color: a.action === 'open' ? (a.direction === 'short' ? '#ef4444' : '#10b981') : '#94a3b8',
      text: `${a.action}\n${a.trade_id}`,
    })), [annotations])

  // Draw new zones/closed-trade lines as they arrive — DrawingManager is
  // imperative (chartRef.addDrawing), so this only ever ADDS, never re-renders
  // existing ones; each annotation gets a stable id so it's only drawn once.
  useEffect(() => {
    const zonesById = new Map<string, PromptWorkbenchZoneAnnotation>()
    const opensByTradeId = new Map<string, PromptWorkbenchTradeAnnotation>()
    for (const a of annotations) {
      if (a.kind === 'zone') zonesById.set(a.zone_id, a)
      else if (a.kind === 'trade' && a.action === 'open') opensByTradeId.set(a.trade_id, a)
    }

    for (const zone of zonesById.values()) {
      const drawingId = `zone_${zone.zone_id}`
      if (renderedDrawingIdsRef.current.has(drawingId)) continue
      const startMs = new Date(zone.start_timestamp).getTime()
      const endMs = new Date(zone.end_timestamp).getTime()
      const inRange = candles.filter(c => {
        const t = new Date(c.timestamp).getTime()
        return t >= Math.min(startMs, endMs) && t <= Math.max(startMs, endMs)
      })
      if (inRange.length === 0) continue
      const high = Math.max(...inRange.map(c => c.high))
      const low = Math.min(...inRange.map(c => c.low))
      const drawing: Drawing = {
        id: drawingId,
        tool: 'rect',
        points: [
          { time: toUnixTime(zone.start_timestamp), price: high },
          { time: toUnixTime(zone.end_timestamp), price: low },
        ],
        style: { color: '#f59e0b', lineStyle: LineStyle.Solid, lineWidth: 1, fillColor: '#f59e0b', fillOpacity: 0.12 },
        label: zone.heading,
        visible: true,
        selected: false,
      }
      chartRef.current?.addDrawing(drawing)
      renderedDrawingIdsRef.current.add(drawingId)
    }

    for (const a of annotations) {
      if (a.kind !== 'trade' || a.action !== 'close') continue
      const openAnn = opensByTradeId.get(a.trade_id)
      const drawingId = `trade_${a.trade_id}`
      if (!openAnn || renderedDrawingIdsRef.current.has(drawingId)) continue
      const candleCountSpan = Math.abs(openAnn.candle_number - a.candle_number)
      const priceDiff = openAnn.direction === 'short' ? openAnn.price - a.price : a.price - openAnn.price
      const pips = priceDiff / pipSize(a.price)
      const drawing: Drawing = {
        id: drawingId,
        tool: 'trendline',
        points: [
          { time: toUnixTime(openAnn.timestamp), price: openAnn.price },
          { time: toUnixTime(a.timestamp), price: a.price },
        ],
        style: { color: pips >= 0 ? '#10b981' : '#ef4444', lineStyle: LineStyle.Solid, lineWidth: 2 },
        label: `${candleCountSpan} candles, ${pips >= 0 ? '+' : ''}${pips.toFixed(1)} pips`,
        visible: true,
        selected: false,
      }
      chartRef.current?.addDrawing(drawing)
      renderedDrawingIdsRef.current.add(drawingId)
    }
  }, [annotations, candles])

  function tradeStatusText(): string {
    if (openTrades.size === 0) return 'Currently no simulated trades are open.'
    const lines = [...openTrades.values()].map(t =>
      `- ${t.trade_id}: ${t.direction?.toUpperCase()} opened at candle #${t.candle_number} (entry ${t.price})`,
    )
    return `Currently open simulated trades:\n${lines.join('\n')}`
  }

  // ── Agent Prompt column ──────────────────────────────────────────────────
  const [promptText, setPromptText] = useState('')
  const [loadFromAgentId, setLoadFromAgentId] = useState('')
  const [llmName, setLlmName] = useState('')

  const loadPromptFromAgent = () => {
    const found = agentPromptOptions.find(o => o.agentId === loadFromAgentId)
    if (found) {
      setPromptText(found.systemPrompt)
      if (found.llm) setLlmName(found.llm)
    }
  }

  // ── Chat — runs against a detached Agent + the same LLM/tool-loop as real agents ─
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [chatInput, setChatInput] = useState('')
  const [sending, setSending] = useState(false)
  const [simBusy, setSimBusy] = useState(false)
  const inputRef = useRef<HTMLTextAreaElement | null>(null)

  const pushMessage = (role: ChatMessage['role'], content: string) => {
    setMessages(prev => [...prev, { id: `${role}-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`, role, content, timestamp: now() }])
  }

  const sendChat = async () => {
    const question = chatInput.trim()
    if (!question || sending) return
    const history = messages.map(m => ({ role: m.role, content: m.content }))
    setChatInput('')
    pushMessage('user', question)
    setSending(true)
    try {
      const resp = await api.promptWorkbenchChat({
        system_prompt: promptText,
        question,
        history,
        pair,
        broker_name: brokerName,
        timeframe,
        candle_count: candleCount,
        visible_count: toolTab === 'simulation' ? visibleCount : undefined,
        llm_name: llmName || undefined,
        allowed_tools: ['calculate_indicator', 'zone_marker', 'trade_marker'],
      })
      pushMessage('assistant', resp.error ? `Error: ${resp.error}` : (resp.answer || '(empty response)'))
      if (resp.annotations?.length) setAnnotations(prev => [...prev, ...resp.annotations])
    } catch (err) {
      pushMessage('assistant', `Error: ${String(err)}`)
    } finally {
      setSending(false)
      inputRef.current?.focus()
    }
  }

  const handleChatKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      void sendChat()
    }
  }

  // ── Step / Run / Stop ────────────────────────────────────────────────────
  const stepOnce = useCallback(async (): Promise<boolean> => {
    if (total === 0) return false
    const current = positionRef.current
    if (current <= 0) return false
    const newPosition = Math.max(0, current - stepSize)
    const newVisibleCount = total - newPosition
    pushMessage('user', `[Step] Sichtbares Fenster: Kerzen ${total}–${newPosition} (${newVisibleCount} von ${total}).`)
    setSimBusy(true)
    try {
      const question = [
        autoTradeStatus ? tradeStatusText() : '',
        `Continue the simulation. Candles up to #${newPosition} (numbered #1=newest .. #${total}=oldest) are now visible.`,
        'Decide whether to open, hold, or close a position given the visible candles, and briefly explain why. '
        + 'Use the trade_marker tool to record any open/close decision.',
      ].filter(Boolean).join('\n')
      const resp = await api.promptWorkbenchChat({
        system_prompt: promptText,
        question,
        history: [],
        pair,
        broker_name: brokerName,
        timeframe,
        candle_count: candleCount,
        visible_count: newVisibleCount,
        llm_name: llmName || undefined,
        allowed_tools: ['calculate_indicator', 'zone_marker', 'trade_marker'],
      })
      pushMessage('assistant', resp.error ? `Error: ${resp.error}` : (resp.answer || '(empty response)'))
      if (resp.annotations?.length) setAnnotations(prev => [...prev, ...resp.annotations])
    } catch (err) {
      pushMessage('assistant', `Error: ${String(err)}`)
    } finally {
      setSimBusy(false)
    }
    positionRef.current = newPosition
    setPosition(newPosition)
    return newPosition > 0
  }, [total, stepSize, autoTradeStatus, promptText, pair, brokerName, timeframe, candleCount, llmName, openTrades])

  const handleStep = () => { void stepOnce() }

  const handleRunToggle = () => {
    if (running) {
      stopRequestedRef.current = true
      setRunning(false)
      return
    }
    stopRequestedRef.current = false
    setRunning(true)
    void (async () => {
      while (!stopRequestedRef.current) {
        const canContinue = await stepOnce()
        if (!canContinue) break
        await sleep(500)
      }
      setRunning(false)
    })()
  }

  const handlePreview = () => {
    if (total === 0) { setSimPreview('Keine Kerzen geladen.'); return }
    const first = candles[0]
    const last = candles[Math.max(0, visibleCount - 1)]
    setSimPreview(JSON.stringify({
      note: 'Platzhalter — die echte Snapshot-Pipeline (tool_blocks/calculation_blocks/assembly_transform_script) folgt in einem späteren Schritt.',
      visible_candles: visibleCount,
      total_candles: total,
      position,
      from_candle_number: total,
      to_candle_number: position,
      window_start: first?.timestamp ?? null,
      window_end: last?.timestamp ?? null,
      auto_trade_status: autoTradeStatus,
    }, null, 2))
  }

  const selectCls = 'bg-gray-800 border border-gray-600 rounded px-1 text-gray-200 text-xs'

  return (
    <div className="flex flex-col h-full overflow-hidden bg-gray-950">
      {/* Workbench config (save/load) — disabled placeholders, wired up later */}
      <div className="flex items-center gap-2 px-3 py-1.5 bg-gray-900/60 border-b border-gray-800 flex-shrink-0">
        <span className="text-xs text-white">Workbench Config:</span>
        <select disabled value={savedConfigName} onChange={e => setSavedConfigName(e.target.value)} className={`${selectCls} opacity-50 cursor-not-allowed`}>
          <option value="">— coming soon —</option>
        </select>
        <button disabled className="px-2 py-0.5 rounded border border-gray-700 bg-gray-900 text-white text-xs opacity-40 cursor-not-allowed">Load</button>
        <button disabled className="px-2 py-0.5 rounded border border-gray-700 bg-gray-900 text-white text-xs opacity-40 cursor-not-allowed">Save</button>
      </div>

      {/* Candle-loading bar */}
      <div className="flex items-center gap-3 px-3 py-2 bg-gray-900 border-b border-gray-700 flex-shrink-0 flex-wrap">
        {brokers.length > 1 ? (
          <select value={brokerName ?? ''} onChange={e => setBrokerName(e.target.value || null)} className={selectCls}>
            {brokers.map(b => <option key={b.name} value={b.name}>{b.short_name ?? b.name}</option>)}
          </select>
        ) : brokers.length === 1 ? (
          <span className="text-xs text-white border border-gray-700 rounded px-2 py-0.5 bg-gray-800">
            {brokers[0].short_name ?? brokers[0].name}
          </span>
        ) : null}

        <select value={pair} onChange={e => setPair(e.target.value)} className={selectCls}>
          {availablePairs.length === 0 && <option value="">Loading…</option>}
          {availablePairs.map(p => <option key={p} value={p}>{p}</option>)}
        </select>

        <div className="flex items-center gap-1">
          {TIMEFRAMES.map(tf => (
            <button
              key={tf}
              onClick={() => setTimeframe(tf)}
              className={[
                'px-2 py-0.5 rounded border text-xs',
                timeframe === tf ? 'bg-emerald-800/40 border-emerald-500 text-emerald-300' : 'bg-gray-900 border-gray-700 text-white hover:text-gray-200',
              ].join(' ')}
            >{tf}</button>
          ))}
        </div>

        <div className="flex items-center gap-1 text-xs text-white">
          <span>Candles</span>
          <input
            type="number" min={20} max={2000} value={candleCount}
            onChange={e => setCandleCount(Math.max(20, Math.min(2000, Number(e.target.value))))}
            className="w-16 bg-gray-800 border border-gray-600 rounded px-1 py-0.5 text-gray-200 text-xs"
          />
        </div>

        <div className="flex items-center gap-1 text-xs text-white opacity-50" title="Kommt später — v1 lädt nur über Anzahl">
          <span>Anchor date</span>
          <input type="date" disabled className="bg-gray-800 border border-gray-600 rounded px-1 py-0.5 text-gray-400 text-xs cursor-not-allowed" />
        </div>

        <button
          onClick={() => void loadCandles()}
          disabled={loading}
          className="px-2 py-1 rounded border border-gray-700 bg-gray-900 text-gray-300 hover:text-white text-xs flex items-center gap-1"
        >
          <RefreshCcw className={`w-3 h-3 ${loading ? 'animate-spin' : ''}`} />
          {loading ? 'Loading…' : 'Load'}
        </button>

        <div className="w-px h-5 bg-gray-700 mx-1" />

        <div className="flex items-center gap-1 text-xs text-white">
          <span>Position</span>
          <input
            type="number" min={0} max={total} value={position}
            onChange={e => setPosition(Math.max(0, Math.min(total, Number(e.target.value))))}
            className="w-16 bg-gray-800 border border-gray-600 rounded px-1 py-0.5 text-gray-200 text-xs"
          />
        </div>
        <div className="flex items-center gap-1 text-xs text-white">
          <span>Step size</span>
          <input
            type="number" min={1} max={200} value={stepSize}
            onChange={e => setStepSize(Math.max(1, Number(e.target.value)))}
            className="w-14 bg-gray-800 border border-gray-600 rounded px-1 py-0.5 text-gray-200 text-xs"
          />
        </div>
        <button
          onClick={handleStep}
          disabled={total === 0 || position <= 0 || running || simBusy}
          className="flex items-center gap-1 px-2 py-1 rounded border border-blue-700 bg-blue-900/30 text-blue-300 hover:bg-blue-900/60 text-xs disabled:opacity-40"
        >
          <StepForward className={`w-3 h-3 ${simBusy ? 'animate-pulse' : ''}`} /> Step
        </button>
        <button
          onClick={handleRunToggle}
          disabled={total === 0 || position <= 0}
          className={[
            'flex items-center gap-1 px-2 py-1 rounded border text-xs disabled:opacity-40',
            running ? 'border-red-600 bg-red-900/30 text-red-300 hover:bg-red-900/60' : 'border-emerald-600 bg-emerald-900/30 text-emerald-300 hover:bg-emerald-900/60',
          ].join(' ')}
        >
          {running ? <><Square className="w-3 h-3" /> Stop</> : <><Play className="w-3 h-3" /> Run</>}
        </button>
        <span className="text-xs text-white">
          sichtbar: {visibleCount} / {total} (Kerzen {total}–{position})
        </span>

        {error && <span className="text-xs text-red-400">Error: {error}</span>}
      </div>

      {/* Chart — the shared window into the loaded candle storage */}
      <div style={{ height: chartHeight }} className="border-b border-gray-700 flex-shrink-0">
        {candles.length > 0 ? (
          <ForexChart
            ref={chartRef}
            candles={candles}
            markers={[...boundaryMarkers, ...tradeMarkers]}
            overlayLines={overlayLines}
            oscillators={oscillators}
            ranges={[]}
            range={Math.min(candleCount, total)}
          />
        ) : (
          <div className="flex items-center justify-center h-full text-xs text-white">
            {loading ? 'Kerzen werden geladen…' : 'Keine Kerzen geladen.'}
          </div>
        )}
      </div>

      {/* Drag handle — resizes the chart vs. the bottom 3-column area */}
      <div
        onMouseDown={e => {
          resizingRef.current = true
          resizeStartYRef.current = e.clientY
          resizeStartHeightRef.current = chartHeight
          e.preventDefault()
        }}
        className="h-1.5 flex-shrink-0 cursor-row-resize bg-gray-700 hover:bg-emerald-600 transition-colors flex items-center justify-center"
      >
        <div className="w-12 h-0.5 bg-gray-500 rounded-full pointer-events-none" />
      </div>

      {/* Bottom: 3 columns — Agent Chat | Tools | Agent Prompt */}
      <div className="flex-1 min-h-0 flex">
        {/* Agent Chat */}
        <section className="flex flex-col min-h-0 w-1/3 border-r border-gray-700">
          <div className="px-3 py-1.5 bg-gray-900 border-b border-gray-800 text-xs text-white font-medium">
            Agent Chat
          </div>
          <div className="flex-1 overflow-y-auto px-3 py-3 space-y-2">
            {messages.length === 0 && (
              <p className="text-xs text-white italic">Ask a question, or use Step/Run above to walk the simulation.</p>
            )}
            {messages.map(msg => (
              <div key={msg.id} className={msg.role === 'user' ? 'flex justify-end' : 'flex justify-start'}>
                <div className={
                  msg.role === 'user'
                    ? 'max-w-[85%] rounded-lg px-3 py-1.5 text-xs bg-emerald-900/50 text-emerald-100 whitespace-pre-wrap'
                    : 'max-w-[90%] rounded-lg px-3 py-1.5 text-xs bg-gray-800 text-gray-200 whitespace-pre-wrap'
                }>
                  {msg.content}
                </div>
              </div>
            ))}
            {(sending || simBusy) && (
              <div className="flex justify-start">
                <div className="bg-gray-800 rounded-lg px-3 py-1.5 text-xs text-gray-400 animate-pulse">
                  Waiting for the agent…
                </div>
              </div>
            )}
          </div>
          <div className="flex-shrink-0 px-3 py-2 border-t border-gray-700 flex gap-2 items-end">
            <textarea
              ref={inputRef}
              value={chatInput}
              onChange={e => setChatInput(e.target.value)}
              onKeyDown={handleChatKeyDown}
              rows={2}
              placeholder="Ask the agent about the loaded chart…"
              className="flex-1 resize-none bg-gray-800 text-gray-200 text-xs rounded px-2 py-1.5 border border-gray-600 focus:outline-none focus:border-emerald-500 placeholder-gray-600"
            />
            <button
              onClick={() => void sendChat()}
              disabled={!chatInput.trim() || sending}
              className="px-3 py-1.5 bg-emerald-700 hover:bg-emerald-600 disabled:bg-gray-700 disabled:text-gray-500 text-white text-xs rounded transition-colors"
            >
              Send
            </button>
          </div>
        </section>

        {/* Tools — [Analyse] / [Simulation] */}
        <section className="flex flex-col min-h-0 w-1/3 border-r border-gray-700">
          <div className="flex items-center border-b border-gray-800 bg-gray-900 flex-shrink-0">
            {(['analyse', 'simulation'] as ToolTab[]).map(tab => (
              <button
                key={tab}
                onClick={() => setToolTab(tab)}
                className={[
                  'px-3 py-1.5 text-xs transition-colors',
                  toolTab === tab ? 'bg-indigo-700 text-white' : 'text-white hover:text-gray-200 hover:bg-gray-800',
                ].join(' ')}
              >
                {tab === 'analyse' ? 'Analyse' : 'Simulation'}
              </button>
            ))}
          </div>
          <div className="flex-1 overflow-y-auto p-3 space-y-3 text-xs">
            {toolTab === 'analyse' ? (
              <>
                <p className="text-white">
                  Kerzendaten-Indikatoren, wie in Chart Analysis — Anzeige direkt im Chart oben. Der Agent bekommt
                  bei einer freien Diskussion die vollständigen Kerzendaten dieses Storages.
                </p>
                <IndicatorsPanel
                  indicators={indicators}
                  onAdd={addIndicator}
                  onRemove={removeIndicator}
                  onUpdate={updateIndicator}
                />
              </>
            ) : (
              <>
                <p className="text-white">
                  Simulation: [Step] schickt den Agenten mit dem aktuell sichtbaren Fenster (Kerzen {total}–{position})
                  echt an die LLM (über einen detached Agent, gleiche Tool-Loop wie live). Die eigentliche
                  Block-Pipeline (tool_blocks / calculation_blocks / assembly_transform_script, wie im Snapshot
                  Designer) folgt in einem späteren Schritt — aktuell stehen `calculate_indicator`, `zone_marker`
                  und `trade_marker` zur Verfügung.
                </p>
                <label className="flex items-center gap-2 cursor-pointer select-none">
                  <input type="checkbox" checked={autoTradeStatus} onChange={e => setAutoTradeStatus(e.target.checked)} className="accent-emerald-500" />
                  <span className={autoTradeStatus ? 'text-emerald-400' : 'text-white'}>Auto Trade-Status einfügen</span>
                </label>
                {openTrades.size > 0 && (
                  <pre className="whitespace-pre-wrap break-words text-[11px] text-emerald-300 leading-5 bg-gray-900/60 border border-gray-800 rounded p-2">
                    {tradeStatusText()}
                  </pre>
                )}
                <button
                  onClick={handlePreview}
                  className="px-2 py-1 rounded border border-gray-700 bg-gray-900 text-white hover:text-gray-200 text-xs"
                >
                  Test / Preview
                </button>
                {simPreview && (
                  <pre className="whitespace-pre-wrap break-words text-[11px] text-gray-300 leading-5 bg-gray-900/60 border border-gray-800 rounded p-2">
                    {simPreview}
                  </pre>
                )}
              </>
            )}
          </div>
        </section>

        {/* Agent Prompt */}
        <section className="flex flex-col min-h-0 w-1/3">
          <div className="flex items-center justify-between px-3 py-1.5 bg-gray-900 border-b border-gray-800 flex-shrink-0 gap-2 flex-wrap">
            <span className="text-xs text-white font-medium flex-shrink-0">Agent Prompt</span>
            <div className="flex items-center gap-1">
              <select value={loadFromAgentId} onChange={e => setLoadFromAgentId(e.target.value)} className={selectCls}>
                <option value="">— load from agent —</option>
                {agentPromptOptions.map(o => <option key={o.agentId} value={o.agentId}>{o.agentId}</option>)}
              </select>
              <button
                onClick={loadPromptFromAgent}
                disabled={!loadFromAgentId}
                className="px-2 py-0.5 rounded border border-gray-700 bg-gray-900 text-white hover:text-gray-200 text-xs disabled:opacity-40"
              >
                Load
              </button>
            </div>
            <div className="flex items-center gap-1">
              <span className="text-xs text-white">LLM:</span>
              <select value={llmName} onChange={e => setLlmName(e.target.value)} className={selectCls} title="LLM used to run the prompt in this Workbench">
                <option value="">— auto —</option>
                {availableLlmNames.map(name => <option key={name} value={name}>{name}</option>)}
              </select>
            </div>
          </div>
          <div className="flex-1 min-h-0">
            <PlainTextMonacoEditor value={promptText} onChange={setPromptText} language="plaintext" />
          </div>
        </section>
      </div>
    </div>
  )
}
