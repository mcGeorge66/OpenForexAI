/**
 * PromptWorkbench (PWB) — sandbox for testing/tuning an Agent's system prompt
 * against historical candle data, independent of the live trading system.
 *
 * Candle loading + numbering, chart, Analyse-tab indicator overlays (reused
 * Chart-Analysis pattern), Snapshot-tab position/step/run mechanics, and
 * the Agent Prompt editor. Chat/Step/Run call `POST /prompt-workbench/chat`,
 * which runs the prompt through a detached (non-registered) `Agent` instance
 * reusing `Agent._run_with_tools` — the same LLM/tool-use loop real agents
 * use, not a second implementation. The agent has `calculate_indicator` plus
 * four sandbox-only tools — `zone_marker`, `trade_marker`, `candle_marker`
 * (write) and `get_annotation` (read, looks up a prior marking + its real
 * candles by id or candle range so the agent can explain itself from actual
 * data instead of confabulating) — which the backend echoes back as
 * structured `annotations`, tagged client-side with whatever color was
 * selected at send time (so overlapping results from different
 * questions/runs stay visually distinguishable) and rendered as chart
 * drawings (reusing the existing rect/trendline DrawingManager primitives,
 * not a new chart feature). Annotations accumulate client-side across
 * turns and are sent back on every request as `existing_annotations`, since
 * the backend keeps no session state of its own. The tool_blocks/
 * calculation_blocks Snapshot pipeline (mini Snapshot Designer, in the
 * Snapshot tab) feeds the exact same assembled snapshot the agent/EC would
 * get in production, anchored to the last visible candle instead of live data.
 *
 * Position semantics (as specified): candles count down from `total`
 * (oldest, at the edge of the loaded window) to `0` (newest / fully
 * revealed). The agent's visible window is always candles `total`..`position`.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { BookOpen, Check, Copy, Play, RefreshCcw, RotateCcw, Square, StepForward, Trash2 } from 'lucide-react'
import { LineStyle } from 'lightweight-charts'
import {
  api,
  type CalculationBlock,
  type CandleBar,
  type InitialConsoleModuleItem,
  type PromptWorkbenchContextPreviewResponse,
  type PromptWorkbenchSavedConfig,
  type PromptWorkbenchToolEvent,
  type ToolInfo,
} from '@/api/client'
import { kbImport } from '@/knowledgebase/kbImport'
import {
  ForexChart,
  type ForexChartHandle,
  type ForexChartMarker,
  type ForexChartOscillator,
  type ForexChartOverlayLine,
  type ForexChartPriceLine,
} from '@/components/charts/ForexChart'
import { useAnnotationOverlay, pipSize, type TaggedAnnotation } from '@/components/charts/useAnnotationOverlay'
import { IndicatorsPanel } from '@/components/charts/IndicatorsPanel'
import {
  INDICATOR_DEFS,
  DEFAULT_COLORS,
  type IndicatorInstance,
  type IndicatorName,
} from '@/components/charts/indicatorDefs'
import { SwingLevelsPanel, type SwingResult } from '@/components/charts/SwingLevelsPanel'
import { PlainTextMonacoEditor } from '@/components/common/PlainTextMonacoEditor'
import { ScriptEditor } from '@/components/common/ScriptEditor'
import { JsonViewer } from '@/components/common/JsonViewer'
import {
  CalculationBlocksPanel,
  ToolBlocksPanel,
} from '@/components/common/SnapshotBlocksPanel'
import {
  defaultArgumentsForTool,
  defaultOutputKey,
  normalizeCalculationBlock,
  normalizeToolBlock,
  serializeCalculationBlock,
  serializeToolBlock,
  type SnapshotToolBlockForm,
} from '@/components/common/snapshotBlocksHelpers'
import { TF_MINUTES } from '@/utils/indicators'

// Analyse-tab indicator config for a saved Workbench Config — deliberately excludes
// `data`/`bbData` (computed values, recalculated fresh against whatever candles the
// config loads) and `id` (regenerated on load).
function serializeIndicatorInstance(ind: IndicatorInstance): Record<string, unknown> {
  return {
    name: ind.name,
    period: ind.period,
    timeframe: ind.timeframe,
    color: ind.color,
    line_style: ind.lineStyle,
    line_width: ind.lineWidth,
    visible: ind.visible,
    ...(ind.smoothPeriod !== undefined ? { smooth_period: ind.smoothPeriod } : {}),
  }
}

function normalizeIndicatorInstance(raw: Record<string, unknown>, index: number): IndicatorInstance | null {
  const name = typeof raw.name === 'string' ? raw.name as IndicatorName : null
  const def = name ? INDICATOR_DEFS.find(d => d.name === name) : undefined
  if (!name || !def) return null
  return {
    id: `ind_${Date.now()}_${index}_${Math.random().toString(36).slice(2, 7)}`,
    name,
    period: typeof raw.period === 'number' ? raw.period : def.defaultPeriod,
    timeframe: typeof raw.timeframe === 'string' ? raw.timeframe : 'M5',
    color: typeof raw.color === 'string' ? raw.color : DEFAULT_COLORS[index % DEFAULT_COLORS.length],
    lineStyle: typeof raw.line_style === 'number' ? raw.line_style : LineStyle.Solid,
    lineWidth: typeof raw.line_width === 'number' ? raw.line_width : 1,
    visible: typeof raw.visible === 'boolean' ? raw.visible : true,
    data: [],
    ...(typeof raw.smooth_period === 'number' ? { smoothPeriod: raw.smooth_period } : {}),
  }
}

const TIMEFRAMES = Object.keys(TF_MINUTES).filter(tf => tf !== 'M1')
const REASONING_EFFORTS = ['none', 'low', 'medium', 'high']

type ToolTab = 'analyse' | 'snapshot' | 'ba' | 'context'

interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  timestamp: string
  // Real captured tool-call events for this turn (assistant messages only) — lets the
  // chat show what the agent actually did, separate from what its answer text claims.
  toolEvents?: PromptWorkbenchToolEvent[]
  // Simulation-step only (AA-decision + BA-script input/result), assistant messages only.
  decision?: Record<string, unknown> | null
  decisionValid?: boolean
  decisionRetries?: number
  decisionDiscarded?: string[]
  scriptInput?: Record<string, unknown> | null
  scriptResult?: Record<string, unknown> | null
  scriptError?: string | null
}

// One line per tool call, e.g. "trade_marker(open) OK" / "trade_marker(close) FAILED".
// Pairs TOOL_CALL_STARTED (has arguments) with the following TOOL_CALL_COMPLETED/FAILED
// for the same tool, in emission order — dispatcher emits them strictly sequentially
// per call, never interleaved, so positional pairing is safe.
function summarizeToolEvents(events: PromptWorkbenchToolEvent[] | undefined): string[] {
  if (!events?.length) return []
  const lines: string[] = []
  let pendingName: string | null = null
  let pendingArgs: Record<string, unknown> | undefined
  for (const evt of events) {
    if (evt.event_type === 'tool_call_started') {
      pendingName = evt.payload.tool_name ?? '?'
      pendingArgs = evt.payload.arguments
      continue
    }
    const name = evt.payload.tool_name ?? pendingName ?? '?'
    const detail = pendingArgs?.action ? `(${pendingArgs.action})` : ''
    // A tool can "complete" (no exception) while its own payload signals a business-level
    // rejection (e.g. trade_marker's FIFO/immutability checks return {"error": ...} instead
    // of raising) — parse the result so those still read as rejected, not OK.
    let status = 'OK'
    if (evt.event_type === 'tool_call_failed') {
      status = 'FAILED'
    } else if (evt.event_type === 'tool_call_completed') {
      try {
        const parsed = JSON.parse(evt.payload.result ?? '{}')
        if (parsed && typeof parsed === 'object' && 'error' in parsed) status = 'REJECTED'
      } catch { /* non-JSON result — treat as OK */ }
    }
    lines.push(`${name}${detail} ${status}`)
    pendingName = null
    pendingArgs = undefined
  }
  return lines
}

function now(): string {
  return new Date().toISOString().replace('T', ' ').substring(11, 19) + ' UTC'
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
      className="inline-flex items-center text-gray-500 hover:text-gray-300 transition-colors flex-shrink-0"
    >
      {copied ? <Check className="w-3 h-3 text-emerald-400" /> : <Copy className="w-3 h-3" />}
    </button>
  )
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
  // Decoupled from candleCount itself — candleCount drives loadCandles (a live
  // network request), so committing on every keystroke would re-fetch on each
  // digit typed. Only commit on blur/Enter.
  const [candleCountInput, setCandleCountInput] = useState('500')
  useEffect(() => { setCandleCountInput(String(candleCount)) }, [candleCount])
  const commitCandleCount = () => {
    const parsed = Number(candleCountInput)
    const clamped = Math.max(20, Math.min(2000, Number.isFinite(parsed) && parsed > 0 ? parsed : candleCount))
    setCandleCount(clamped)
    setCandleCountInput(String(clamped))
  }
  // datetime-local string (YYYY-MM-DDTHH:mm), naive wall-clock — same convention as
  // ChartAnalysis.tsx's anchorDateTime/anchorIso, so a saved simulation anchor means
  // exactly the same point in time there and here.
  const [anchorDate, setAnchorDate] = useState('')
  const anchorIso = useMemo(() => anchorDate ? `${anchorDate}:00` : null, [anchorDate])
  const [candles, setCandles] = useState<CandleBar[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const chartRef = useRef<ForexChartHandle | null>(null)

  // ISO timestamp of the newest candle in the currently loaded window, captured once
  // per Load — sent with every chat/step/preview request so the backend re-derives
  // this exact frozen window instead of a fresh live fetch. The loaded chart is the
  // single source of truth for the whole session; it must never silently drift as
  // real time passes between messages, whether or not an Anchor date was set.
  const candleAnchorRef = useRef<string | null>(null)

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

  const snapshotProfileOptions = useMemo(() => {
    const profiles = (systemConfig?.snapshot_profiles ?? {}) as Record<string, Record<string, unknown>>
    return Object.entries(profiles)
      .map(([name, cfg]) => ({
        name,
        toolBlocks: Array.isArray(cfg.tool_blocks) ? cfg.tool_blocks : [],
        calculationBlocks: Array.isArray(cfg.calculation_blocks) ? cfg.calculation_blocks : [],
        assemblyScript: typeof cfg.assembly_transform_script === 'string' ? cfg.assembly_transform_script : '',
      }))
      .sort((a, b) => a.name.localeCompare(b.name))
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
          ...(anchorIso ? { start: anchorIso } : {}),
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
  }, [candleCount, pair, timeframe, brokerName, anchorIso])

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

  // ── Agent-drawn annotation state — declared before loadCandles, which calls
  // clearAnnotations() on every fresh candle set (stale zones/trade lines from
  // a previous load no longer apply). Rendering itself (state, DrawingManager
  // diffing, marker derivation) lives in useAnnotationOverlay, shared with the
  // Chart Analysis assistant so both render zone_marker/trade_marker/candle_marker
  // tool calls identically instead of two implementations.
  const {
    annotations, annotationsRef, annotationColor, setAnnotationColor,
    clearAnnotations, applyAnnotationUpdates, markers: annotationMarkers,
  } = useAnnotationOverlay(chartRef, candles)

  const loadCandles = useCallback(async () => {
    if (!pair) return
    setLoading(true)
    setError(null)
    try {
      const data = await api.getCandles(pair, timeframe, candleCount, brokerName, anchorIso)
      setCandles(data)
      candleAnchorRef.current = data.length > 0
        ? data.reduce((newest, c) => c.timestamp > newest ? c.timestamp : newest, data[0].timestamp)
        : null
      setPosition(0) // fully revealed by default; lower it to set up a simulation start point
      const updated = await recomputeIndicators(data, indicatorsRef.current)
      setIndicators(updated)
      // Fresh candle set — stale zones/trade lines from a previous load no longer apply.
      clearAnnotations()
    } catch (err) {
      setError(String(err))
    } finally {
      setLoading(false)
    }
  }, [pair, timeframe, candleCount, brokerName, anchorIso, recomputeIndicators, clearAnnotations])

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

  // ── Analyse-tab swing levels — same shared panel/tool as Chart Analysis, but
  // ALWAYS anchored to the visible window (candles[visibleCount-1], the same
  // boundary the rest of the Workbench already treats as "now") instead of
  // Chart Analysis's candle-count-derived lookback against live data — the
  // loaded chart must stay the single source of truth, not silently query live
  // data for this one feature while everything else stays frozen.
  const [swingEnabled, setSwingEnabled] = useState(false)
  const [swingTf, setSwingTf] = useState('H1')
  const [swingCount, setSwingCount] = useState(5)
  const [swingAtrPeriod, setSwingAtrPeriod] = useState(14)
  const [swingMinGapAtr, setSwingMinGapAtr] = useState(0.3)
  const [swingLineWidth, setSwingLineWidth] = useState(2)
  const [swingLineStyle, setSwingLineStyle] = useState<LineStyle>(LineStyle.Dashed)
  const [swingPriceSource, setSwingPriceSource] = useState<'HL' | 'OC'>('HL')
  const [swingSortBy, setSwingSortBy] = useState<'nearest' | 'prominent'>('nearest')
  const swingSortByRef = useRef<'nearest' | 'prominent'>('nearest')
  useEffect(() => { swingSortByRef.current = swingSortBy }, [swingSortBy])
  const [swingLines, setSwingLines] = useState<ForexChartPriceLine[]>([])
  const [swingLoading, setSwingLoading] = useState(false)

  const loadSwingLevels = useCallback(async () => {
    if (!pair || !swingEnabled || visibleCount === 0) { setSwingLines([]); return }
    setSwingLoading(true)
    try {
      const anchor = candles[visibleCount - 1]?.timestamp
      const chartMinutes = visibleCount * (TF_MINUTES[timeframe] ?? 5)
      const swingLookback = Math.max(10, Math.ceil(chartMinutes / (TF_MINUTES[swingTf] ?? 60)))
      const res = await api.executeTool('get_swing_levels', {
        timeframe: swingTf, max_levels: swingCount, lookback: swingLookback,
        atr_period: swingAtrPeriod, min_gap_atr: swingMinGapAtr,
        price_source: swingPriceSource, sort_by: swingSortByRef.current,
        ...(anchor ? { start: anchor } : {}),
      }, null, brokerName, null, pair)
      const result = res.result as SwingResult
      const lines: ForexChartPriceLine[] = [
        ...(result.highs ?? []).map(h => ({
          price: h.price, title: `SH ${h.price.toFixed(5)}`, color: '#10b981',
          lineStyle: swingLineStyle, lineWidth: swingLineWidth,
        })),
        ...(result.lows ?? []).map(l => ({
          price: l.price, title: `SL ${l.price.toFixed(5)}`, color: '#ef4444',
          lineStyle: swingLineStyle, lineWidth: swingLineWidth,
        })),
        ...(result.confluence ?? []).map(c => ({
          price: c.price, title: `SH/SL ${c.price.toFixed(5)}`, color: '#f97316',
          lineStyle: swingLineStyle, lineWidth: Math.min(swingLineWidth + 1, 4),
        })),
      ]
      setSwingLines(lines)
    } catch {
      setSwingLines([])
    } finally {
      setSwingLoading(false)
    }
  }, [pair, swingEnabled, swingTf, swingCount, swingAtrPeriod, swingMinGapAtr, visibleCount, candles, timeframe, swingLineWidth, swingLineStyle, swingPriceSource, brokerName])

  useEffect(() => { void loadSwingLevels() }, [loadSwingLevels])

  // ── Left column tab — [Chat] / [Prompt] ─────────────────────────────────
  const [leftTab, setLeftTab] = useState<'chat' | 'prompt' | 'ec'>('chat')
  // Which one Step/Run actually executes — independent of which of the Prompt/EC tabs is
  // currently being viewed, so you can review the prompt while EC mode is what's running.
  const [step1Mode, setStep1Mode] = useState<'agent' | 'ec'>('agent')
  const [ecScript, setEcScript] = useState('')
  const [ecScriptConfigText, setEcScriptConfigText] = useState('{}')
  const [ecScriptAllowedTools, setEcScriptAllowedTools] = useState<string[]>([])

  // ── Tools tab ────────────────────────────────────────────────────────────
  const [toolTab, setToolTab] = useState<ToolTab>('analyse')
  // FIFO: mirrors brokers that only allow closing the oldest open position first —
  // enforced server-side in trade_marker, not just a UI label.
  const [fifoEnabled, setFifoEnabled] = useState(false)
  // Off by default: a recorded trade leg mirrors a real broker fill, which can't be
  // un-sent — enforced server-side in trade_marker, not just a UI label.
  const [allowTradeDelete, setAllowTradeDelete] = useState(false)
  // AA-under-test's tool access for Step/Run. Empty = decision-only via
  // Agent._run_decision_only_cycle — the same method production AA agents use for
  // their real decision call (data already gathered, LLM's only job is the JSON
  // decision). Non-empty runs the normal tool loop instead, for testing an AA
  // variant that fetches its own context.
  const [simulationAllowedTools, setSimulationAllowedTools] = useState<string[]>([])
  // BA-simulation: a deterministic script (not a second LLM call) that receives the
  // AA's decision and decides whether/how to act on it, drawing the outcome via
  // trade_marker — mirrors the real AA→BA split, with the BA played by user code
  // instead of a second agent for fast, cheap iteration.
  const [decisionScript, setDecisionScript] = useState('')
  const [decisionScriptConfigText, setDecisionScriptConfigText] = useState('{}')
  const [decisionScriptAllowedTools, setDecisionScriptAllowedTools] = useState<string[]>(['assessment_memory', 'trade_marker'])
  // Key the script uses with assessment_memory to persist state (e.g. current
  // simulated position) across steps and sessions — the script controls the actual
  // get/set calls, this is just the key it's told to use.
  const [memoryKey, setMemoryKey] = useState('')
  // Latest simulate-step result, shown as a persistent viewer in the BA tab itself
  // (not just buried per-message in the chat) — always reflects the most recent
  // Step/Run tick, so it's visible right next to the script you're editing.
  const [lastStepResult, setLastStepResult] = useState<{
    decision?: Record<string, unknown> | null
    decisionValid?: boolean
    decisionRetries?: number
    decisionDiscarded?: string[]
    scriptInput?: Record<string, unknown> | null
    scriptResult?: Record<string, unknown> | null
    scriptError?: string | null
  } | null>(null)
  const [simPreview, setSimPreview] = useState<
    { kind: 'notice'; text: string } | { kind: 'result'; snapshot: Record<string, unknown>; errors: string[] } | null
  >(null)
  const [simPreviewLoading, setSimPreviewLoading] = useState(false)
  // "Letzter Input" viewer at the bottom of the EC tab — the exact `input`/`snapshot` the EC-tab
  // script received, so both the user and the LLM Script Assistant see the real shape instead of
  // guessing. Populated by a Step/Run in EC mode (both fields) and by the Snapshot tab's
  // Test/Preview button (snapshot only, ahead of ever running a step — see handlePreview).
  const [lastEcInput, setLastEcInput] = useState<Record<string, unknown> | null>(null)
  const [lastEcSnapshot, setLastEcSnapshot] = useState<Record<string, unknown> | null>(null)
  // Fed into the EC-tab ScriptEditor's LLM Script Assistant as contextData, so it sees the
  // real input/snapshot shape instead of guessing — same idea as EntityAssistantPanel's
  // testInput/testResult props in the production Entity Config Wizard.
  const ecScriptContextData = useMemo(() => {
    if (!lastEcInput && !lastEcSnapshot) return undefined
    const parts: string[] = []
    if (lastEcInput) parts.push(`=== Letzter Input ('input' param) ===\n${JSON.stringify(lastEcInput, null, 2)}`)
    if (lastEcSnapshot) parts.push(`=== 'snapshot' global ===\n${JSON.stringify(lastEcSnapshot, null, 2)}`)
    return parts.join('\n\n')
  }, [lastEcInput, lastEcSnapshot])

  // Simulation tab: mini Snapshot Designer — same tool_blocks/calculation_blocks/
  // assembly_transform_script editing UI as the real Snapshot Designer
  // (SnapshotBlocksPanel), reused rather than a second hand-rolled editor.
  const [snapshotProfileName, setSnapshotProfileName] = useState('')
  const [toolBlocksState, setToolBlocksState] = useState<SnapshotToolBlockForm[]>([])
  const [calculationBlocksState, setCalculationBlocksState] = useState<CalculationBlock[]>([])
  const [assemblyScriptText, setAssemblyScriptText] = useState('')
  const [availableTools, setAvailableTools] = useState<ToolInfo[]>([])
  const [blockTestResults, setBlockTestResults] = useState<Record<string, { loading?: boolean; text?: string; error?: string }>>({})

  useEffect(() => {
    void api.getTools().then(r => setAvailableTools(r.tools)).catch(() => setAvailableTools([]))
  }, [])

  const loadSnapshotProfile = () => {
    const found = snapshotProfileOptions.find(o => o.name === snapshotProfileName)
    if (!found) return
    setToolBlocksState(found.toolBlocks.map((b, i) => normalizeToolBlock(b, i)).filter((b): b is SnapshotToolBlockForm => b !== null))
    setCalculationBlocksState(found.calculationBlocks.map((b, i) => normalizeCalculationBlock(b, i)).filter((b): b is CalculationBlock => b !== null))
    setAssemblyScriptText(found.assemblyScript)
  }

  const addToolBlockRow = (toolName: string) => {
    setToolBlocksState(prev => [...prev, {
      _reactKey: crypto.randomUUID(),
      id: `block_${prev.length + 1}`,
      tool_name: toolName,
      output_key: defaultOutputKey(toolName, prev.length),
      enabled: true,
      arguments: defaultArgumentsForTool(toolName),
      transform_script: '',
    }])
  }
  const removeToolBlockRow = (index: number) => setToolBlocksState(prev => prev.filter((_b, i) => i !== index))
  const updateToolBlockRow = (index: number, patch: Partial<SnapshotToolBlockForm>) =>
    setToolBlocksState(prev => prev.map((b, i) => i === index ? { ...b, ...patch } : b))
  const updateToolBlockArgumentRow = (index: number, argName: string, value: string) =>
    setToolBlocksState(prev => prev.map((b, i) => i === index ? { ...b, arguments: { ...b.arguments, [argName]: value } } : b))

  const addCalcBlockRow = () => setCalculationBlocksState(prev => [...prev, {
    id: `calc_${prev.length + 1}`, type: 'script', enabled: true, sources: {}, config: {}, script: '',
  }])
  const removeCalcBlockRow = (index: number) => setCalculationBlocksState(prev => prev.filter((_b, i) => i !== index))
  const updateCalcBlockRow = (index: number, patch: Partial<CalculationBlock>) =>
    setCalculationBlocksState(prev => prev.map((b, i) => i === index ? { ...b, ...patch } : b))

  // Per-block Test — reuses /prompt-workbench/snapshot-preview with just the
  // one block (tool block) or all tool blocks + just the one calc block
  // (calc blocks read tool outputs), no separate backend endpoint needed.
  const testToolBlock = async (index: number) => {
    const block = toolBlocksState[index]
    if (!block) return
    setBlockTestResults(prev => ({ ...prev, [block._reactKey]: { loading: true } }))
    try {
      const resp = await api.promptWorkbenchSnapshotPreview({
        pair, broker_name: brokerName, timeframe, candle_count: candleCount, visible_count: visibleCount,
        candle_anchor: candleAnchorRef.current,
        tool_blocks: [serializeToolBlock(block, index)],
        calculation_blocks: [],
        assembly_transform_script: '',
      })
      const output = resp.snapshot?.tool_outputs as Record<string, unknown> | undefined
      const text = resp.errors.length
        ? resp.errors.join('\n')
        : JSON.stringify(output?.[block.output_key] ?? resp.snapshot, null, 2)
      setBlockTestResults(prev => ({ ...prev, [block._reactKey]: { text } }))
    } catch (err) {
      setBlockTestResults(prev => ({ ...prev, [block._reactKey]: { error: String(err) } }))
    }
  }

  const testCalcBlock = async (index: number) => {
    const block = calculationBlocksState[index]
    if (!block) return
    const key = `${block.id}-${index}`
    setBlockTestResults(prev => ({ ...prev, [key]: { loading: true } }))
    try {
      const resp = await api.promptWorkbenchSnapshotPreview({
        pair, broker_name: brokerName, timeframe, candle_count: candleCount, visible_count: visibleCount,
        candle_anchor: candleAnchorRef.current,
        tool_blocks: toolBlocksState.map((b, i) => serializeToolBlock(b, i)),
        calculation_blocks: [serializeCalculationBlock(block)],
        assembly_transform_script: '',
      })
      const calc = resp.snapshot?.calculations as Record<string, unknown> | undefined
      const text = resp.errors.length ? resp.errors.join('\n') : JSON.stringify(calc ?? resp.snapshot, null, 2)
      setBlockTestResults(prev => ({ ...prev, [key]: { text } }))
    } catch (err) {
      setBlockTestResults(prev => ({ ...prev, [key]: { error: String(err) } }))
    }
  }

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
    if ((toolTab !== 'snapshot' && toolTab !== 'ba') || total === 0 || position <= 0 || position >= total) return []
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

  // ── Agent-drawn annotations (zone_marker / trade_marker / candle_marker) ──
  // Accumulated client-side across turns — the backend keeps no session state,
  // each response only returns the annotations created during that one call.
  // State, tagAnnotations/applyAnnotationUpdates, marker derivation, and the
  // DrawingManager zone/trade-line rendering all live in useAnnotationOverlay
  // now (destructured above) — kept here is only what's PWB-specific: which
  // trades are currently open, for tradeStatusText below.
  const openTrades = useMemo(() => {
    const open = new Map<string, Extract<TaggedAnnotation, { kind: 'trade' }>>()
    for (const a of annotations) {
      if (a.kind !== 'trade') continue
      if (a.action === 'open') open.set(a.trade_id, a)
      else open.delete(a.trade_id)
    }
    return open
  }, [annotations])

  const tradeStatusText = useCallback((): string => {
    if (openTrades.size === 0) return 'Currently no simulated trades are open.'
    const lines = [...openTrades.values()].map(t =>
      `- ${t.trade_id}: ${t.direction?.toUpperCase()} opened at candle #${t.candle_number} (entry ${t.price})`,
    )
    return `Currently open simulated trades:\n${lines.join('\n')}`
  }, [openTrades])

  // One row per trade_id (open+close legs merged), for the BA tab's "Trades" viewer — same
  // pips calculation already used for the chart's closed-trade trendline label (see the
  // annotations-diffing effect above), just surfaced as a list with a running total instead
  // of only drawn on the chart.
  const tradeRows = useMemo(() => {
    const opensByTradeId = new Map<string, Extract<TaggedAnnotation, { kind: 'trade' }>>()
    const closesByTradeId = new Map<string, Extract<TaggedAnnotation, { kind: 'trade' }>>()
    for (const a of annotations) {
      if (a.kind !== 'trade') continue
      if (a.action === 'open') opensByTradeId.set(a.trade_id, a)
      else closesByTradeId.set(a.trade_id, a)
    }
    const rows = [...opensByTradeId.values()].map(openAnn => {
      const closeAnn = closesByTradeId.get(openAnn.trade_id)
      const pips = closeAnn
        ? (openAnn.direction === 'short' ? openAnn.price - closeAnn.price : closeAnn.price - openAnn.price) / pipSize(closeAnn.price)
        : undefined
      return {
        tradeId: openAnn.trade_id,
        direction: openAnn.direction,
        openCandle: openAnn.candle_number,
        openPrice: openAnn.price,
        closeCandle: closeAnn?.candle_number,
        closePrice: closeAnn?.price,
        pips,
        note: closeAnn?.note ?? openAnn.note,
      }
    })
    // Chronological (oldest first) — candle numbering is #1=newest .. #total=oldest.
    rows.sort((a, b) => b.openCandle - a.openCandle)
    return rows
  }, [annotations])

  const tradeSummary = useMemo(() => {
    const closed = tradeRows.filter(r => r.pips !== undefined)
    const totalPips = closed.reduce((sum, r) => sum + (r.pips ?? 0), 0)
    return {
      openCount: tradeRows.length - closed.length,
      closedCount: closed.length,
      totalPips,
      wins: closed.filter(r => (r.pips ?? 0) > 0).length,
      losses: closed.filter(r => (r.pips ?? 0) < 0).length,
    }
  }, [tradeRows])

  // ── Agent Prompt column ──────────────────────────────────────────────────
  const [promptText, setPromptText] = useState('')
  const [loadFromAgentId, setLoadFromAgentId] = useState('')
  const [llmName, setLlmName] = useState('')
  const [reasoningEffort, setReasoningEffort] = useState('low')

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
  const [chatKbMsg, setChatKbMsg] = useState<string | null>(null)
  const inputRef = useRef<HTMLTextAreaElement | null>(null)
  const messagesContainerRef = useRef<HTMLDivElement | null>(null)
  const prevMessageCountRef = useRef(0)
  const scrollAnchorRef = useRef<HTMLElement | null>(null)

  // Scroll to bottom on every new message — unless the anchor (the first newly
  // appended message; see below) is taller than the visible history, in which
  // case scroll just far enough that its top edge lines up with the top of the
  // history area, so its beginning stays readable instead of being scrolled past.
  const applyScrollAnchor = (container: HTMLDivElement, anchorEl: HTMLElement | null) => {
    if (!anchorEl) return
    // Don't use anchorEl.offsetTop — it's relative to the nearest positioned
    // offsetParent, not to this container (which isn't itself `position`d), so
    // it silently measures against some ancestor far up the page instead of
    // the scroll area. getBoundingClientRect gives both elements' positions in
    // the same (viewport) coordinate space, so the delta is container-relative.
    const anchorTop = anchorEl.getBoundingClientRect().top - container.getBoundingClientRect().top + container.scrollTop
    const remaining = container.scrollHeight - anchorTop
    if (remaining <= container.clientHeight) {
      container.scrollTop = container.scrollHeight
    } else {
      container.scrollTop = anchorTop
    }
  }

  useEffect(() => {
    const container = messagesContainerRef.current
    if (!container) return
    // Anchor to the first message added since the last run, not the last DOM
    // child — a reply can arrive together with a second "Snapshot errors" bubble
    // in the same batch, and anchoring to that trailing (short) bubble would
    // scroll the actual answer above it clean out of view.
    const children = container.children
    const anchorEl = (children[prevMessageCountRef.current] as HTMLElement | undefined)
      ?? (children[children.length - 1] as HTMLElement | undefined)
      ?? null
    scrollAnchorRef.current = anchorEl
    applyScrollAnchor(container, anchorEl)
    prevMessageCountRef.current = messages.length
  }, [messages])

  // Re-apply the same alignment when the panel is resized (e.g. dragging the
  // chart/chat divider) — a size change alone doesn't touch `messages`, so the
  // effect above wouldn't otherwise re-run.
  useEffect(() => {
    const container = messagesContainerRef.current
    if (!container) return
    const observer = new ResizeObserver(() => {
      applyScrollAnchor(container, scrollAnchorRef.current)
    })
    observer.observe(container)
    return () => observer.disconnect()
  }, [])

  const pushMessage = (
    role: ChatMessage['role'],
    content: string,
    extra?: {
      toolEvents?: PromptWorkbenchToolEvent[]
      decision?: Record<string, unknown> | null
      decisionValid?: boolean
      decisionRetries?: number
      decisionDiscarded?: string[]
      scriptInput?: Record<string, unknown> | null
      scriptResult?: Record<string, unknown> | null
      scriptError?: string | null
    },
  ) => {
    setMessages(prev => [...prev, {
      id: `${role}-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`, role, content, timestamp: now(),
      ...extra,
    }])
  }

  // Clears only the chat transcript — chart drawings have their own dedicated
  // "Clear chart" button (clearAnnotations) in the toolbar above, kept separate.
  const clearChatHistory = () => {
    setMessages([])
  }

  const handleChatKbImport = useCallback(async () => {
    const transcript = messages
      .map(m => `## ${m.role === 'user' ? 'User' : 'Assistant'} (${m.timestamp})\n${m.content}`)
      .join('\n\n')
    const md = `# Simulation Chat — ${pair} / ${timeframe}

**Broker:** ${brokerName ?? '–'} · **Messages:** ${messages.length}

${transcript}`

    try {
      await kbImport('PromptWorkbenchChat', md)
      setChatKbMsg('✓ In Knowledgebase gespeichert')
      setTimeout(() => setChatKbMsg(null), 2000)
    } catch (e) {
      pushMessage('assistant', `KB Import failed: ${String(e)}`)
    }
  }, [messages, pair, timeframe, brokerName])

  // Only sent when the Simulation/BA tabs have tool_blocks configured — otherwise
  // the agent keeps getting raw candle text, unchanged from before.
  const snapshotPipelineFields = useCallback(() => {
    if ((toolTab !== 'snapshot' && toolTab !== 'ba') || toolBlocksState.length === 0) return {}
    return {
      tool_blocks: toolBlocksState.map((b, i) => serializeToolBlock(b, i)),
      calculation_blocks: calculationBlocksState.map(b => serializeCalculationBlock(b)),
      assembly_transform_script: assemblyScriptText,
    }
  }, [toolTab, toolBlocksState, calculationBlocksState, assemblyScriptText])

  // ── LLM Context tab — live preview of exactly what /prompt-workbench/chat
  // would send, via the same backend context-builder (no LLM call). Unlike
  // snapshotPipelineFields() (gated on the Simulation tab being focused, so a
  // filled-in tool_blocks config can be bypassed by switching tabs), this
  // reflects tool_blocks whenever any are configured — the tab itself isn't
  // "focus-gated" since it's a separate, persistent preview.
  const [contextPreview, setContextPreview] = useState<PromptWorkbenchContextPreviewResponse | null>(null)
  const [contextPreviewLoading, setContextPreviewLoading] = useState(false)
  const [contextPreviewError, setContextPreviewError] = useState<string | null>(null)

  useEffect(() => {
    if (toolTab !== 'context' || !pair || candles.length === 0) return
    const timer = setTimeout(() => {
      setContextPreviewLoading(true)
      setContextPreviewError(null)
      const toolBlocksFields = toolBlocksState.length > 0
        ? {
            tool_blocks: toolBlocksState.map((b, i) => serializeToolBlock(b, i)),
            calculation_blocks: calculationBlocksState.map(b => serializeCalculationBlock(b)),
            assembly_transform_script: assemblyScriptText,
          }
        : {}
      void api.promptWorkbenchContextPreview({
        system_prompt: promptText,
        question: chatInput,
        history: [],
        pair,
        broker_name: brokerName,
        timeframe,
        candle_count: candleCount,
        candle_anchor: candleAnchorRef.current,
        visible_count: position > 0 ? visibleCount : undefined,
        indicators: indicators.filter(ind => ind.visible).map(ind => ({
          name: ind.name,
          period: ind.period,
          timeframe: ind.timeframe,
          last_value: ind.data.length > 0 ? ind.data[ind.data.length - 1].value : null,
        })),
        swing_levels: swingEnabled ? swingLines.map(l => ({ title: l.title, price: l.price })) : [],
        ...toolBlocksFields,
      })
        .then(setContextPreview)
        .catch(err => setContextPreviewError(String(err)))
        .finally(() => setContextPreviewLoading(false))
    }, 500)
    return () => clearTimeout(timer)
  }, [
    toolTab, pair, brokerName, timeframe, candleCount, candles, position, visibleCount,
    indicators, swingEnabled, swingLines, promptText, chatInput,
    toolBlocksState, calculationBlocksState, assemblyScriptText,
  ])

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
        candle_anchor: candleAnchorRef.current,
        visible_count: (toolTab === 'snapshot' || toolTab === 'ba') ? visibleCount : undefined,
        llm_name: llmName || undefined,
        reasoning_effort: reasoningEffort,
        allowed_tools: ['calculate_indicator', 'zone_marker', 'trade_marker', 'candle_marker', 'get_annotation'],
        existing_annotations: annotations,
        indicators: indicators.filter(ind => ind.visible).map(ind => ({
          name: ind.name,
          period: ind.period,
          timeframe: ind.timeframe,
          last_value: ind.data.length > 0 ? ind.data[ind.data.length - 1].value : null,
        })),
        swing_levels: swingEnabled ? swingLines.map(l => ({ title: l.title, price: l.price })) : [],
        fifo_enabled: fifoEnabled,
        allow_trade_delete: allowTradeDelete,
        ...snapshotPipelineFields(),
      })
      pushMessage('assistant', resp.error ? `Error: ${resp.error}` : (resp.answer || '(empty response)'), { toolEvents: resp.tool_events })
      if (resp.snapshot_errors?.length) pushMessage('assistant', `Snapshot errors:\n${resp.snapshot_errors.join('\n')}`)
      applyAnnotationUpdates(resp)
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
        `Continue the simulation. Candles up to #${newPosition} (numbered #1=newest .. #${total}=oldest) are now visible.`,
        'Give your independent market assessment as strict JSON only — no prose outside the JSON, no tool calls: '
        + '{"decision": "BIAS_LONG"|"BIAS_SHORT"|"NEUTRAL", "confidence": 0-100, "reasoning": "...", '
        + '"invalidation_level": <price>, "target": <price>}. '
        + 'Assess the chart on its own merits each time — you are not managing a position, only reading the market.',
      ].join('\n')
      let decisionScriptConfig: Record<string, unknown> = {}
      try {
        decisionScriptConfig = decisionScript.trim() ? JSON.parse(decisionScriptConfigText) : {}
      } catch (err) {
        pushMessage('assistant', `Script Config ist kein gültiges JSON, wird als {} behandelt: ${String(err)}`)
      }
      let ecScriptConfig: Record<string, unknown> = {}
      try {
        ecScriptConfig = step1Mode === 'ec' ? JSON.parse(ecScriptConfigText) : {}
      } catch (err) {
        pushMessage('assistant', `EC Script Config ist kein gültiges JSON, wird als {} behandelt: ${String(err)}`)
      }
      const resp = await api.promptWorkbenchSimulateStep({
        system_prompt: promptText,
        question,
        history: [],
        pair,
        broker_name: brokerName,
        timeframe,
        candle_count: candleCount,
        candle_anchor: candleAnchorRef.current,
        visible_count: newVisibleCount,
        llm_name: llmName || undefined,
        reasoning_effort: reasoningEffort,
        allowed_tools: simulationAllowedTools,
        // Read via ref, not the closed-over `annotations` state — see annotationsRef's comment:
        // Run calls this function in a loop using one stale closure, so the state value here
        // would otherwise never reflect trades opened/closed by earlier steps in the same Run.
        existing_annotations: annotationsRef.current,
        indicators: indicators.filter(ind => ind.visible).map(ind => ({
          name: ind.name,
          period: ind.period,
          timeframe: ind.timeframe,
          last_value: ind.data.length > 0 ? ind.data[ind.data.length - 1].value : null,
        })),
        swing_levels: swingEnabled ? swingLines.map(l => ({ title: l.title, price: l.price })) : [],
        fifo_enabled: fifoEnabled,
        allow_trade_delete: allowTradeDelete,
        decision_script: decisionScript,
        decision_script_config: decisionScriptConfig,
        decision_script_allowed_tools: decisionScriptAllowedTools,
        memory_key: memoryKey,
        step1_mode: step1Mode,
        ec_script: ecScript,
        ec_script_config: ecScriptConfig,
        ec_script_allowed_tools: ecScriptAllowedTools,
        ...snapshotPipelineFields(),
      })
      pushMessage('assistant', resp.error ? `Error: ${resp.error}` : (resp.answer || '(empty response)'), {
        toolEvents: resp.tool_events, decision: resp.decision,
        decisionValid: resp.decision_valid, decisionRetries: resp.decision_retries,
        decisionDiscarded: resp.decision_discarded, scriptInput: resp.script_input,
        scriptResult: resp.script_result, scriptError: resp.script_error,
      })
      setLastStepResult({
        decision: resp.decision, decisionValid: resp.decision_valid, decisionRetries: resp.decision_retries,
        decisionDiscarded: resp.decision_discarded, scriptInput: resp.script_input,
        scriptResult: resp.script_result, scriptError: resp.script_error,
      })
      if (resp.ec_input) setLastEcInput(resp.ec_input)
      if (resp.snapshot) setLastEcSnapshot(resp.snapshot)
      if (resp.snapshot_errors?.length) pushMessage('assistant', `Snapshot errors:\n${resp.snapshot_errors.join('\n')}`)
      applyAnnotationUpdates(resp)
    } catch (err) {
      pushMessage('assistant', `Error: ${String(err)}`)
    } finally {
      setSimBusy(false)
    }
    positionRef.current = newPosition
    setPosition(newPosition)
    return newPosition > 0
  }, [
    total, stepSize, fifoEnabled, allowTradeDelete, simulationAllowedTools, decisionScript, decisionScriptConfigText,
    decisionScriptAllowedTools, memoryKey, promptText, pair, brokerName, timeframe, candleCount, llmName,
    reasoningEffort, applyAnnotationUpdates, annotationsRef, indicators, swingEnabled, swingLines, snapshotPipelineFields,
    step1Mode, ecScript, ecScriptConfigText, ecScriptAllowedTools,
  ])

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

  const handlePreview = async () => {
    if (total === 0) { setSimPreview({ kind: 'notice', text: 'Keine Kerzen geladen.' }); return }
    if (toolBlocksState.length === 0) {
      setSimPreview({ kind: 'notice', text: 'Keine tool_blocks konfiguriert — Profil laden oder Tool hinzufügen.' })
      return
    }
    setSimPreviewLoading(true)
    try {
      const resp = await api.promptWorkbenchSnapshotPreview({
        pair, broker_name: brokerName, timeframe, candle_count: candleCount,
        visible_count: visibleCount,
        candle_anchor: candleAnchorRef.current,
        tool_blocks: toolBlocksState.map((b, i) => serializeToolBlock(b, i)),
        calculation_blocks: calculationBlocksState.map(b => serializeCalculationBlock(b)),
        assembly_transform_script: assemblyScriptText,
      })
      setSimPreview({ kind: 'result', snapshot: resp.snapshot, errors: resp.errors })
      // Pre-fills the EC tab's "Letzter Input" viewer with the snapshot half even before any
      // Step/Run happened — see that viewer's comment for why this button can do that.
      setLastEcSnapshot(resp.snapshot)
    } catch (err) {
      setSimPreview({ kind: 'notice', text: `Error: ${String(err)}` })
    } finally {
      setSimPreviewLoading(false)
    }
  }

  // ── Workbench config save/load/delete — setup only, no session state (see
  // PromptWorkbenchSavedConfig). Same whole-array GET/PUT pattern as the
  // prompt/snippet libraries: delete just removes the entry client-side and
  // PUTs the remaining array back, no dedicated delete endpoint.
  const [savedConfigs, setSavedConfigs] = useState<PromptWorkbenchSavedConfig[]>([])
  const [configMsg, setConfigMsg] = useState<string | null>(null)

  useEffect(() => {
    void api.getPromptWorkbenchConfigs().then(lib => setSavedConfigs(lib.configs)).catch(() => setSavedConfigs([]))
  }, [])

  const flashConfigMsg = (text: string) => {
    setConfigMsg(text)
    setTimeout(() => setConfigMsg(null), 2000)
  }

  const handleLoadConfig = () => {
    const found = savedConfigs.find(c => c.name === savedConfigName)
    if (!found) return
    setBrokerName(found.broker_name ?? null)
    setPair(found.pair)
    setTimeframe(found.timeframe)
    setCandleCount(found.candle_count)
    // Configs saved before the anchor field gained a time component stored a plain
    // "YYYY-MM-DD" date, which a datetime-local input can't display — fall back to
    // the old fixed end-of-day time so those saved anchors still resolve to what they
    // used to mean, instead of showing up blank.
    setAnchorDate(/^\d{4}-\d{2}-\d{2}$/.test(found.anchor_date) ? `${found.anchor_date}T23:59` : found.anchor_date)
    setAnnotationColor(found.annotation_color)
    setStepSize(found.step_size)
    setFifoEnabled(found.fifo_enabled ?? false)
    setAllowTradeDelete(found.allow_trade_delete ?? false)
    setSimulationAllowedTools(found.simulation_allowed_tools ?? [])
    setDecisionScript(found.decision_script ?? '')
    setDecisionScriptConfigText(JSON.stringify(found.decision_script_config ?? {}, null, 2))
    setDecisionScriptAllowedTools(found.decision_script_allowed_tools ?? ['assessment_memory', 'trade_marker'])
    setMemoryKey(found.memory_key ?? '')
    setStep1Mode(found.step1_mode ?? 'agent')
    setEcScript(found.ec_script ?? '')
    setEcScriptConfigText(JSON.stringify(found.ec_script_config ?? {}, null, 2))
    setEcScriptAllowedTools(found.ec_script_allowed_tools ?? [])
    setLeftTab(found.left_tab)
    // Backward-compat: configs saved before the Simulation->Snapshot rename still contain
    // the literal string "simulation" on disk (JSON5, not type-checked at runtime).
    setToolTab((found.tool_tab as string) === 'simulation' ? 'snapshot' : found.tool_tab)
    setPromptText(found.system_prompt)
    setLlmName(found.llm_name)
    setReasoningEffort(found.reasoning_effort)
    setIndicators(
      (found.indicators ?? [])
        .map((ind, i) => normalizeIndicatorInstance(ind, i))
        .filter((ind): ind is IndicatorInstance => ind !== null),
    )
    setToolBlocksState(found.tool_blocks.map((b, i) => normalizeToolBlock(b, i)).filter((b): b is SnapshotToolBlockForm => b !== null))
    setCalculationBlocksState(found.calculation_blocks.map((b, i) => normalizeCalculationBlock(b, i)).filter((b): b is CalculationBlock => b !== null))
    setAssemblyScriptText(found.assembly_transform_script)
  }

  const handleSaveConfig = async () => {
    const name = savedConfigName.trim()
    if (!name) return
    const entry: PromptWorkbenchSavedConfig = {
      name,
      broker_name: brokerName,
      pair,
      timeframe,
      candle_count: candleCount,
      anchor_date: anchorDate,
      annotation_color: annotationColor,
      step_size: stepSize,
      fifo_enabled: fifoEnabled,
      allow_trade_delete: allowTradeDelete,
      left_tab: leftTab,
      // "context" is a live preview tab, not a persisted workbench mode —
      // fall back to "analyse" so the saved-config schema stays unchanged.
      tool_tab: toolTab === 'context' ? 'analyse' : toolTab,
      system_prompt: promptText,
      llm_name: llmName,
      reasoning_effort: reasoningEffort,
      indicators: indicators.map(ind => serializeIndicatorInstance(ind)),
      tool_blocks: toolBlocksState.map((b, i) => serializeToolBlock(b, i)),
      calculation_blocks: calculationBlocksState.map(b => serializeCalculationBlock(b)),
      assembly_transform_script: assemblyScriptText,
      simulation_allowed_tools: simulationAllowedTools,
      decision_script: decisionScript,
      decision_script_config: (() => { try { return JSON.parse(decisionScriptConfigText) } catch { return {} } })(),
      decision_script_allowed_tools: decisionScriptAllowedTools,
      memory_key: memoryKey,
      step1_mode: step1Mode,
      ec_script: ecScript,
      ec_script_config: (() => { try { return JSON.parse(ecScriptConfigText) } catch { return {} } })(),
      ec_script_allowed_tools: ecScriptAllowedTools,
    }
    const next = [...savedConfigs.filter(c => c.name !== name), entry]
    try {
      await api.savePromptWorkbenchConfigs({ configs: next })
      setSavedConfigs(next)
      flashConfigMsg('✓ Saved')
    } catch (err) {
      flashConfigMsg(`Save failed: ${String(err)}`)
    }
  }

  const handleDeleteConfig = async () => {
    const name = savedConfigName.trim()
    if (!name || !savedConfigs.some(c => c.name === name)) return
    const next = savedConfigs.filter(c => c.name !== name)
    try {
      await api.savePromptWorkbenchConfigs({ configs: next })
      setSavedConfigs(next)
      setSavedConfigName('')
      flashConfigMsg('✓ Deleted')
    } catch (err) {
      flashConfigMsg(`Delete failed: ${String(err)}`)
    }
  }

  // Resets the whole Workbench to a blank slate — everything a saved config
  // covers, plus candles/chat/annotations/simulation state a config doesn't
  // (those were never part of Save/Load, so New has to clear them itself).
  const handleNewWorkbench = () => {
    setSavedConfigName('')
    setBrokerName(null)
    setPair('')
    setTimeframe('M5')
    setCandleCount(500)
    setAnchorDate('')
    setCandles([])
    setIndicators([])
    clearAnnotations()
    setPosition(0)
    setStepSize(3)
    setRunning(false)
    setLastStepResult(null)
    setLeftTab('chat')
    setToolTab('analyse')
    setFifoEnabled(false)
    setAllowTradeDelete(false)
    setSimulationAllowedTools([])
    setDecisionScript('')
    setDecisionScriptConfigText('{}')
    setDecisionScriptAllowedTools(['assessment_memory', 'trade_marker'])
    setMemoryKey('')
    setStep1Mode('agent')
    setEcScript('')
    setEcScriptConfigText('{}')
    setEcScriptAllowedTools([])
    setSimPreview(null)
    setSnapshotProfileName('')
    setToolBlocksState([])
    setCalculationBlocksState([])
    setAssemblyScriptText('')
    setBlockTestResults({})
    setPromptText('')
    setLoadFromAgentId('')
    setLlmName('')
    setReasoningEffort('low')
    setMessages([])
    setChatInput('')
  }

  const selectCls = 'bg-gray-800 border border-gray-600 rounded px-1 text-gray-200 text-xs'

  return (
    <div className="flex flex-col h-full overflow-hidden bg-gray-950">
      {/* Workbench config (save/load/delete) — setup only, see PromptWorkbenchSavedConfig */}
      <div className="flex items-center gap-2 px-3 py-1.5 bg-gray-900/60 border-b border-gray-800 flex-shrink-0">
        <span className="text-xs text-white">Workbench Config:</span>
        <button
          onClick={handleNewWorkbench}
          title="Alles zurücksetzen — leerer Workbench"
          className="px-2 py-0.5 rounded border border-gray-700 bg-gray-900 text-white text-xs hover:text-gray-200"
        >
          New
        </button>
        <input
          list="workbench-config-names"
          value={savedConfigName}
          onChange={e => setSavedConfigName(e.target.value)}
          placeholder="pick or type a name…"
          className={`${selectCls} w-48`}
        />
        <datalist id="workbench-config-names">
          {savedConfigs.map(c => <option key={c.name} value={c.name} />)}
        </datalist>
        <button
          onClick={handleLoadConfig}
          disabled={!savedConfigs.some(c => c.name === savedConfigName)}
          className="px-2 py-0.5 rounded border border-gray-700 bg-gray-900 text-white text-xs disabled:opacity-40 disabled:cursor-not-allowed hover:text-gray-200"
        >
          Load
        </button>
        <button
          onClick={() => void handleSaveConfig()}
          disabled={!savedConfigName.trim()}
          className="px-2 py-0.5 rounded border border-gray-700 bg-gray-900 text-white text-xs disabled:opacity-40 disabled:cursor-not-allowed hover:text-gray-200"
        >
          Save
        </button>
        <button
          onClick={() => void handleDeleteConfig()}
          disabled={!savedConfigs.some(c => c.name === savedConfigName)}
          className="px-2 py-0.5 rounded border border-gray-700 bg-gray-900 text-white text-xs disabled:opacity-40 disabled:cursor-not-allowed hover:text-red-400"
        >
          Delete
        </button>
        {configMsg && <span className="text-xs text-emerald-400">{configMsg}</span>}
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
            type="number" min={20} max={2000} value={candleCountInput}
            onChange={e => setCandleCountInput(e.target.value)}
            onBlur={commitCandleCount}
            onKeyDown={e => {
              if (e.key !== 'Enter') return
              e.preventDefault()
              commitCandleCount()
              ;(e.target as HTMLInputElement).blur()
            }}
            title="Wert übernehmen mit Enter oder beim Verlassen des Felds"
            className="w-11 bg-gray-800 border border-gray-600 rounded px-1 py-0.5 text-gray-200 text-xs"
          />
        </div>

        <div className="flex items-center gap-1 text-xs text-white" title="Optional: Kerzen bis zu diesem Zeitpunkt laden statt der aktuellsten. Leer lassen für Live-Daten.">
          <span>Anchor</span>
          <input
            type="datetime-local"
            value={anchorDate}
            onChange={e => setAnchorDate(e.target.value)}
            className="bg-gray-800 border border-gray-600 rounded px-1 py-0.5 text-gray-200 text-xs"
          />
          {anchorDate && (
            <button
              onClick={() => setAnchorDate('')}
              title="Anchor zurücksetzen (Live-Daten)"
              className="text-gray-500 hover:text-gray-300"
            >
              ×
            </button>
          )}
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
            className="w-11 bg-gray-800 border border-gray-600 rounded px-1 py-0.5 text-gray-200 text-xs"
          />
        </div>
        <div className="flex items-center gap-1 text-xs text-white">
          <span>Step size</span>
          <input
            type="number" min={1} max={200} value={stepSize}
            onChange={e => setStepSize(Math.max(1, Number(e.target.value)))}
            className="w-7 bg-gray-800 border border-gray-600 rounded px-1 py-0.5 text-gray-200 text-xs [appearance:textfield] [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none"
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
        {position > 0 && (
          <span className="text-xs text-white">
            sichtbar: {visibleCount} / {total} (Kerzen {total}–{position})
          </span>
        )}

        <button
          onClick={clearAnnotations}
          disabled={annotations.length === 0}
          title="Remove all zones/trades the agent drew on the chart"
          className="flex items-center gap-1 px-2 py-1 rounded border border-gray-700 bg-gray-900 text-gray-300 hover:text-white text-xs disabled:opacity-40"
        >
          <Trash2 className="w-3 h-3" /> Clear chart
        </button>

        <button
          onClick={() => chartRef.current?.resetView()}
          disabled={total === 0}
          title="Zoom/Pan zurücksetzen — alle geladenen Kerzen wieder sichtbar"
          className="flex items-center gap-1 px-2 py-1 rounded border border-gray-700 bg-gray-900 text-gray-300 hover:text-white text-xs disabled:opacity-40"
        >
          <RotateCcw className="w-3 h-3" /> Reset
        </button>

        {error && <span className="text-xs text-red-400">Error: {error}</span>}
      </div>

      {/* Chart — the shared window into the loaded candle storage */}
      <div style={{ height: chartHeight }} className="border-b border-gray-700 flex-shrink-0">
        {candles.length > 0 ? (
          <ForexChart
            ref={chartRef}
            candles={candles}
            markers={[...boundaryMarkers, ...annotationMarkers]}
            overlayLines={overlayLines}
            oscillators={oscillators}
            priceLines={swingLines}
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

      {/* Bottom: 2 columns — [Chat/Prompt] | Tools */}
      <div className="flex-1 min-h-0 flex">
        {/* Left column — [Chat] / [Prompt] */}
        <section className="flex flex-col min-h-0 w-1/2 border-r border-gray-700">
          <div className="flex items-center justify-between border-b border-gray-800 bg-gray-900 flex-shrink-0">
            <div className="flex items-center">
              {(['chat', 'prompt', 'ec'] as const).map(tab => (
                <button
                  key={tab}
                  onClick={() => setLeftTab(tab)}
                  className={[
                    'px-3 py-1.5 text-xs transition-colors uppercase',
                    leftTab === tab ? 'bg-indigo-700 text-white' : 'text-white hover:text-gray-200 hover:bg-gray-800',
                  ].join(' ')}
                >
                  {tab === 'chat' ? 'Chat' : tab === 'prompt' ? 'Prompt' : 'EC'}
                </button>
              ))}
            </div>
            <div
              className="flex items-center gap-0.5 mr-2 rounded border border-gray-700 overflow-hidden"
              title="Was Step/Run tatsächlich ausführt — unabhängig davon, welcher Tab links gerade angezeigt wird. Agent = LLM (Prompt-Tab), EC = deterministisches Skript (EC-Tab), kein LLM."
            >
              {(['agent', 'ec'] as const).map(mode => (
                <button
                  key={mode}
                  onClick={() => setStep1Mode(mode)}
                  className={[
                    'px-2 py-1 text-[10px] transition-colors',
                    step1Mode === mode ? 'bg-emerald-700 text-white' : 'bg-gray-950 text-white hover:text-gray-200',
                  ].join(' ')}
                >
                  {mode === 'agent' ? 'Prompt' : 'EC'}
                </button>
              ))}
            </div>
          </div>

          {leftTab === 'chat' ? (
            <>
              <div className="flex items-center justify-between px-3 py-1.5 bg-gray-900 border-b border-gray-800 text-xs text-white font-medium">
                {chatKbMsg
                  ? <span className="text-xs text-emerald-400 border border-emerald-700 rounded px-2 py-0.5 bg-emerald-900/20">{chatKbMsg}</span>
                  : <button
                      onClick={() => void handleChatKbImport()}
                      disabled={messages.length === 0}
                      className="px-2 py-1 rounded border border-gray-700 bg-gray-900 text-gray-300 hover:text-white text-xs flex items-center gap-1 disabled:opacity-40"
                      title="Gesamten Chatverlauf in der Knowledgebase [Import] speichern"
                    >
                      <BookOpen className="w-3 h-3" /> → KB
                    </button>
                }
                <div className="flex items-center gap-1.5">
                  <button
                    onClick={clearChatHistory}
                    disabled={messages.length === 0}
                    title="Chatverlauf löschen"
                    className="flex items-center gap-1 px-2 py-1 rounded border border-gray-700 bg-gray-900 text-gray-300 hover:text-white text-xs disabled:opacity-40"
                  >
                    <Trash2 className="w-3 h-3" /> Delete
                  </button>
                  <input
                    type="color"
                    value={annotationColor}
                    onChange={e => setAnnotationColor(e.target.value)}
                    title="Color used for zones/trade/candle markers drawn from now on"
                    className="w-6 h-6 cursor-pointer rounded border-0 bg-transparent"
                  />
                  <select
                    value={reasoningEffort}
                    onChange={e => setReasoningEffort(e.target.value)}
                    title="Reasoning effort — compare behavior across levels"
                    className={selectCls}
                  >
                    {REASONING_EFFORTS.map(level => <option key={level} value={level}>{level}</option>)}
                  </select>
                </div>
              </div>
              <div ref={messagesContainerRef} className="flex-1 overflow-y-auto px-3 py-3 space-y-2">
                {messages.length === 0 && (
                  <p className="text-xs text-white italic">Ask a question, or use Step/Run above to walk the simulation.</p>
                )}
                {messages.map(msg => {
                  const toolLines = msg.role === 'assistant' ? summarizeToolEvents(msg.toolEvents) : []
                  return (
                  <div key={msg.id} className={msg.role === 'user' ? 'flex justify-end' : 'flex justify-start items-start gap-1'}>
                    <div className={
                      msg.role === 'user'
                        ? 'max-w-[85%] rounded-lg px-3 py-1.5 text-xs bg-emerald-900/50 text-emerald-100 whitespace-pre-wrap'
                        : 'max-w-[90%] rounded-lg px-3 py-1.5 text-xs bg-gray-800 text-gray-200 whitespace-pre-wrap'
                    }>
                      {msg.content}
                      {toolLines.length > 0 && (
                        <div
                          className="mt-1.5 pt-1.5 border-t border-gray-700 text-[10px] text-white font-mono"
                          title="Tatsächlich ausgeführte Tool-Aufrufe dieser Antwort — nicht vom Antworttext abgeleitet"
                        >
                          Tools: {toolLines.join(', ')}
                        </div>
                      )}
                      {msg.decision !== undefined && (
                        <details className="mt-1.5 pt-1.5 border-t border-gray-700 text-[10px] text-white font-mono">
                          <summary
                            className="cursor-pointer select-none text-gray-400 hover:text-white"
                            title="Die geparste AA-Entscheidung dieses Schritts — inkl. Retry-Info, falls die Antwort erst nach Korrektur valides JSON war"
                          >
                            Decision
                            {(msg.decisionRetries ?? 0) > 0 && ` — ${msg.decisionRetries}× retried`}
                            {msg.decisionValid === false && ' — INVALID after all retries'}
                          </summary>
                          <pre className="mt-1 whitespace-pre-wrap break-all">
                            {msg.decision ? JSON.stringify(msg.decision, null, 2) : '(invalid — no JSON could be parsed)'}
                          </pre>
                          {(msg.decisionDiscarded?.length ?? 0) > 0 && (
                            <div className="mt-1.5 pt-1.5 border-t border-gray-800 space-y-1">
                              <div className="text-gray-500">Discarded attempts:</div>
                              {msg.decisionDiscarded!.map((text, i) => (
                                <pre key={i} className="whitespace-pre-wrap break-all text-red-300/80 bg-gray-900/50 rounded px-1 py-0.5 mb-1">
                                  {text}
                                </pre>
                              ))}
                            </div>
                          )}
                        </details>
                      )}
                      {msg.scriptInput && (
                        <details className="mt-1.5 pt-1.5 border-t border-gray-700 text-[10px] text-white font-mono">
                          <summary
                            className="cursor-pointer select-none text-gray-400 hover:text-white"
                            title="Das exakte 'input'-JSON, das an das BA Decision Script übergeben wurde — backend-erzeugt, nicht editierbar"
                          >
                            Script Input
                          </summary>
                          <pre className="mt-1 whitespace-pre-wrap break-all">{JSON.stringify(msg.scriptInput, null, 2)}</pre>
                        </details>
                      )}
                    </div>
                    {msg.role === 'assistant' && (
                      <div className="pt-1.5">
                        <CopyButton getText={() => msg.content} />
                      </div>
                    )}
                  </div>
                  )
                })}
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
            </>
          ) : leftTab === 'prompt' ? (
            <>
              <div className="flex items-center justify-between px-3 py-1.5 bg-gray-900 border-b border-gray-800 flex-shrink-0 gap-2 flex-wrap">
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
            </>
          ) : (
            <div className="flex-1 min-h-0 overflow-y-auto p-3 space-y-3 text-xs">
              <p className="text-white">
                Step 1 als Event Composer statt Agent — inhaltlich und technisch identisch mit einer echten
                EC-Entity (siehe Config → Entity Config): gleicher Vertrag (<code>async def main(input, config,
                tools)</code>), gleiche injizierte Globals (<code>log</code>, <code>emit</code>, <code>debug</code>,
                <code>message</code>, <code>ask_llm</code>). Bekommt kein <code>decision</code>/<code>raw_response</code> —
                das hier ist der erste Schritt, ohne vorgeschaltete AA. Aktiv nur, wenn oben rechts "EC" gewählt ist.
              </p>
              <div className="space-y-1">
                <span className="text-white">EC Script (async def main(input, config, tools))</span>
                <ScriptEditor
                  value={ecScript}
                  onChange={setEcScript}
                  minHeight={180}
                  snippetScope="ec"
                  contextFile="script_pwb_ec_context.md"
                  contextData={ecScriptContextData}
                />
              </div>
              <div className="space-y-1">
                <span className="text-white">Script Config (JSON)</span>
                <textarea
                  value={ecScriptConfigText}
                  onChange={e => setEcScriptConfigText(e.target.value)}
                  rows={4}
                  spellCheck={false}
                  className="w-full bg-gray-900 border border-gray-700 rounded px-2 py-1 text-xs text-gray-200 font-mono"
                />
              </div>
              <details className="space-y-1">
                <summary className="text-white cursor-pointer select-none">
                  EC Tool Access
                  {ecScriptAllowedTools.length > 0 && ` (${ecScriptAllowedTools.length})`}
                </summary>
                <div className="flex flex-wrap gap-1 mt-1">
                  {[...availableTools].sort((a, b) => a.name.localeCompare(b.name)).map(t => (
                    <button
                      key={t.name}
                      type="button"
                      title={t.description}
                      onClick={() => setEcScriptAllowedTools(prev =>
                        prev.includes(t.name) ? prev.filter(n => n !== t.name) : [...prev, t.name],
                      )}
                      className={`px-2 py-0.5 rounded border text-xs ${
                        ecScriptAllowedTools.includes(t.name)
                          ? 'bg-emerald-800/40 border-emerald-500 text-emerald-300'
                          : 'bg-gray-900 border-gray-700 text-white hover:text-gray-200'
                      }`}
                    >
                      {t.name}
                    </button>
                  ))}
                </div>
              </details>

              {(lastEcInput || lastEcSnapshot) ? (
                <div className="space-y-1 border-t border-gray-800 pt-2">
                  <span className="text-white">Letzter Input</span>
                  {lastEcInput && (
                    <details className="text-[11px] text-white font-mono bg-gray-900/60 border border-gray-800 rounded p-2" open>
                      <summary
                        className="cursor-pointer select-none text-gray-400 hover:text-white"
                        title="Das exakte 'input'-JSON, das dem EC-Script im letzten Step/Run übergeben wurde — backend-erzeugt, nicht editierbar"
                      >
                        input
                      </summary>
                      <JsonViewer data={lastEcInput} defaultExpandLevel={2} className="mt-1" />
                    </details>
                  )}
                  {lastEcSnapshot && (
                    <details className="text-[11px] text-white font-mono bg-gray-900/60 border border-gray-800 rounded p-2">
                      <summary
                        className="cursor-pointer select-none text-gray-400 hover:text-white"
                        title="Der `snapshot`-Global, den das EC-Script bekommt, wenn im Snapshot-Tab tool_blocks konfiguriert sind — via Step/Run oder Test/Preview im Snapshot-Tab befüllt"
                      >
                        snapshot
                      </summary>
                      <JsonViewer data={lastEcSnapshot} defaultExpandLevel={2} className="mt-1" />
                    </details>
                  )}
                </div>
              ) : (
                <p className="text-white italic text-xs border-t border-gray-800 pt-2">
                  Noch kein Input — erscheint hier nach dem ersten Step/Run (EC-Modus) oder nach
                  "Test / Preview" im Snapshot-Tab.
                </p>
              )}
            </div>
          )}
        </section>

        {/* Tools — [Analyse] / [Snapshot] */}
        <section className="flex flex-col min-h-0 w-1/2">
          <div className="flex items-center border-b border-gray-800 bg-gray-900 flex-shrink-0">
            {(['analyse', 'snapshot', 'ba', 'context'] as ToolTab[]).map(tab => (
              <button
                key={tab}
                onClick={() => setToolTab(tab)}
                className={[
                  'px-3 py-1.5 text-xs transition-colors',
                  toolTab === tab ? 'bg-indigo-700 text-white' : 'text-white hover:text-gray-200 hover:bg-gray-800',
                ].join(' ')}
              >
                {tab === 'analyse' ? 'Analyse' : tab === 'snapshot' ? 'Snapshot' : tab === 'ba' ? 'BA' : 'LLM Context'}
              </button>
            ))}
          </div>
          <div className="flex-1 overflow-y-auto p-3 space-y-3 text-xs">
            {toolTab === 'analyse' ? (
              <>
                <p className="text-white">
                  Kerzendaten-Indikatoren und Swing Levels, wie in Chart Analysis — Anzeige direkt im Chart oben.
                  Bei einer freien Diskussion (kein Snapshot-Profil) bekommt der Agent die vollständigen Kerzendaten
                  dieses Storages sowie die hier sichtbaren Indikatoren/Swing Levels als Text mit — siehe LLM-Context-Tab.
                </p>
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
                  sortBy={swingSortBy}
                  onSortByChange={s => { swingSortByRef.current = s; setSwingSortBy(s); void loadSwingLevels() }}
                  loading={swingLoading}
                  onReload={() => void loadSwingLevels()}
                  lines={swingLines}
                />
              </>
            ) : toolTab === 'snapshot' ? (
              <>
                <p className="text-white">
                  Snapshot: [Step]/[Run] und Chat schicken dem Agenten den echten, per
                  tool_blocks/calculation_blocks/assembly_transform_script assemblierten Snapshot (gleiche Pipeline
                  wie im Snapshot Designer), verankert auf die zuletzt sichtbare Kerze (#{position || total}) statt
                  auf Live-Daten — sobald hier tool_blocks eingetragen sind. Leer lassen, um weiterhin die rohen
                  Kerzendaten zu verwenden.
                </p>

                <div className="flex items-center gap-1">
                  <select value={snapshotProfileName} onChange={e => setSnapshotProfileName(e.target.value)} className={selectCls}>
                    <option value="">— load from snapshot profile —</option>
                    {snapshotProfileOptions.map(o => <option key={o.name} value={o.name}>{o.name}</option>)}
                  </select>
                  <button
                    onClick={loadSnapshotProfile}
                    disabled={!snapshotProfileName}
                    className="px-2 py-0.5 rounded border border-gray-700 bg-gray-900 text-white hover:text-gray-200 text-xs disabled:opacity-40"
                  >
                    Load
                  </button>
                </div>

                <div className="space-y-1">
                  <span className="text-white">tool_blocks</span>
                  <ToolBlocksPanel
                    blocks={toolBlocksState}
                    tools={availableTools}
                    onAdd={addToolBlockRow}
                    onRemove={removeToolBlockRow}
                    onUpdate={updateToolBlockRow}
                    onUpdateArgument={updateToolBlockArgumentRow}
                    onTest={index => void testToolBlock(index)}
                    testResultByKey={blockTestResults}
                  />
                </div>
                <div className="space-y-1">
                  <span className="text-white">calculation_blocks (optional)</span>
                  <CalculationBlocksPanel
                    blocks={calculationBlocksState}
                    onAdd={addCalcBlockRow}
                    onRemove={removeCalcBlockRow}
                    onUpdate={updateCalcBlockRow}
                    onTest={index => void testCalcBlock(index)}
                    testResultByKey={blockTestResults}
                  />
                </div>
                <div className="space-y-1">
                  <span className="text-white">assembly_transform_script (optional)</span>
                  <ScriptEditor
                    value={assemblyScriptText}
                    onChange={setAssemblyScriptText}
                    minHeight={100}
                    snippetScope="snapshot"
                    contextFile="script_snapshot_assembly_context.md"
                  />
                </div>
                <button
                  onClick={() => void handlePreview()}
                  disabled={simPreviewLoading}
                  className="px-2 py-1 rounded border border-gray-700 bg-gray-900 text-white hover:text-gray-200 text-xs disabled:opacity-40"
                >
                  {simPreviewLoading ? 'Testing…' : 'Test / Preview'}
                </button>
                {simPreview?.kind === 'notice' && (
                  <p className="whitespace-pre-wrap break-words text-[11px] text-gray-300 leading-5 bg-gray-900/60 border border-gray-800 rounded p-2">
                    {simPreview.text}
                  </p>
                )}
                {simPreview?.kind === 'result' && (
                  <div className="bg-gray-900/60 border border-gray-800 rounded p-2">
                    {simPreview.errors.length > 0 && (
                      <div className="mb-1.5 pb-1.5 border-b border-gray-800 text-[11px] text-red-400 whitespace-pre-wrap break-words">
                        === Errors ===
                        {'\n'}{simPreview.errors.join('\n')}
                      </div>
                    )}
                    <JsonViewer data={simPreview.snapshot} defaultExpandLevel={2} />
                  </div>
                )}
              </>
            ) : toolTab === 'ba' ? (
              <>
                <p className="text-white">
                  BA-Simulation: bildet den echten AA→BA-Ablauf nach. Die Agentin (Prompt-Tab) liefert bei
                  Step/Run nur noch eine Entscheidung — ohne eigenen Tool-Zugriff läuft sie über den exakten
                  Aufruf, den Produktions-AA-Agenten für ihre Entscheidung nutzen. Das Skript unten spielt die
                  BA-Rolle: es bekommt diese Entscheidung, entscheidet deterministisch ob/wie gehandelt wird, und
                  zeichnet das Ergebnis über trade_marker ins Chart.
                </p>

                <details className="space-y-1">
                  <summary
                    className="text-white cursor-pointer select-none"
                    title="Tool-Zugriff der AA-Agentin während Step/Run. Leer = reine Entscheidung ohne Tools (Agent._run_decision_only_cycle) — exakt der Aufruf, den echte AA-Agenten für ihre Entscheidung nutzen."
                  >
                    AA Tool Access (Step/Run) — leer = Decision-Only wie in Produktion
                    {simulationAllowedTools.length > 0 && ` (${simulationAllowedTools.length})`}
                  </summary>
                  <div className="flex flex-wrap gap-1 mt-1">
                    {[...availableTools].sort((a, b) => a.name.localeCompare(b.name)).map(t => (
                      <button
                        key={t.name}
                        type="button"
                        title={t.description}
                        onClick={() => setSimulationAllowedTools(prev =>
                          prev.includes(t.name) ? prev.filter(n => n !== t.name) : [...prev, t.name],
                        )}
                        className={`px-2 py-0.5 rounded border text-xs ${
                          simulationAllowedTools.includes(t.name)
                            ? 'bg-emerald-800/40 border-emerald-500 text-emerald-300'
                            : 'bg-gray-900 border-gray-700 text-white hover:text-gray-200'
                        }`}
                      >
                        {t.name}
                      </button>
                    ))}
                  </div>
                </details>

                <div className="space-y-1">
                  <span className="text-white" title="Deterministisches Skript, das die AA-Entscheidung bekommt und die BA-Rolle simuliert: entscheidet ob/wie gehandelt wird, zeichnet das Ergebnis via trade_marker.">
                    BA Decision Script (async def main(input, config, tools))
                  </span>
                  <ScriptEditor
                    value={decisionScript}
                    onChange={setDecisionScript}
                    minHeight={140}
                    snippetScope="ec"
                    contextFile="script_pwb_decision_context.md"
                  />
                </div>
                <div className="space-y-1">
                  <span className="text-white">Script Config (JSON)</span>
                  <textarea
                    value={decisionScriptConfigText}
                    onChange={e => setDecisionScriptConfigText(e.target.value)}
                    rows={4}
                    spellCheck={false}
                    className="w-full bg-gray-900 border border-gray-700 rounded px-2 py-1 text-xs text-gray-200 font-mono"
                  />
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-white" title="Wird als config['memory_key'] ans Skript übergeben — dein Skript nutzt es selbst mit assessment_memory, um Zustand über Schritte/Sitzungen hinweg zu speichern.">
                    Memory Key
                  </span>
                  <input
                    type="text" value={memoryKey} onChange={e => setMemoryKey(e.target.value)}
                    placeholder="z. B. eurusd_krieger_v1"
                    className="flex-1 bg-gray-800 border border-gray-600 rounded px-2 py-1 text-xs text-gray-200 placeholder-gray-600"
                  />
                </div>
                <details className="space-y-1">
                  <summary className="text-white cursor-pointer select-none">
                    BA Script Tool Access
                    {decisionScriptAllowedTools.length > 0 && ` (${decisionScriptAllowedTools.length})`}
                  </summary>
                  <div className="flex flex-wrap gap-1 mt-1">
                    {[...availableTools].sort((a, b) => a.name.localeCompare(b.name)).map(t => (
                      <button
                        key={t.name}
                        type="button"
                        title={t.description}
                        onClick={() => setDecisionScriptAllowedTools(prev =>
                          prev.includes(t.name) ? prev.filter(n => n !== t.name) : [...prev, t.name],
                        )}
                        className={`px-2 py-0.5 rounded border text-xs ${
                          decisionScriptAllowedTools.includes(t.name)
                            ? 'bg-emerald-800/40 border-emerald-500 text-emerald-300'
                            : 'bg-gray-900 border-gray-700 text-white hover:text-gray-200'
                        }`}
                      >
                        {t.name}
                      </button>
                    ))}
                  </div>
                </details>

                <label
                  className="flex items-center gap-2 cursor-pointer select-none"
                  title="Wenn aktiv, muss der älteste noch offene Trade zuerst geschlossen werden, bevor ein neuerer geschlossen werden darf — wie bei FIFO-pflichtigen Brokern."
                >
                  <input type="checkbox" checked={fifoEnabled} onChange={e => setFifoEnabled(e.target.checked)} className="accent-emerald-500" />
                  <span className={fifoEnabled ? 'text-emerald-400' : 'text-white'}>FIFO aktivieren</span>
                </label>
                <label
                  className="flex items-center gap-2 cursor-pointer select-none"
                  title="Standardmäßig aus: ein aufgezeichneter Trade gilt als beim Broker ausgeführt und kann nicht gelöscht, nur geschlossen werden."
                >
                  <input type="checkbox" checked={allowTradeDelete} onChange={e => setAllowTradeDelete(e.target.checked)} className="accent-emerald-500" />
                  <span className={allowTradeDelete ? 'text-emerald-400' : 'text-white'}>delete of trades accepted</span>
                </label>
                {openTrades.size > 0 && (
                  <pre className="whitespace-pre-wrap break-words text-[11px] text-emerald-300 leading-5 bg-gray-900/60 border border-gray-800 rounded p-2">
                    {tradeStatusText()}
                  </pre>
                )}

                {tradeRows.length > 0 && (
                  <details className="text-[11px] text-white font-mono bg-gray-900/60 border border-gray-800 rounded p-2 border-t border-gray-800 pt-2" open>
                    <summary
                      className="cursor-pointer select-none text-gray-400 hover:text-white"
                      title="Alle in dieser Session gesetzten Trades (offen + geschlossen), mit Pips-Ergebnis für bereits geschlossene — dieselbe Berechnung wie am Trendline-Label im Chart."
                    >
                      Trades — {tradeSummary.closedCount} geschlossen, {tradeSummary.openCount} offen
                      {tradeSummary.closedCount > 0 && (
                        <span className={tradeSummary.totalPips >= 0 ? 'text-emerald-400' : 'text-red-400'}>
                          {` · ${tradeSummary.totalPips >= 0 ? '+' : ''}${tradeSummary.totalPips.toFixed(1)} pips`}
                          {` (${tradeSummary.wins}W/${tradeSummary.losses}L)`}
                        </span>
                      )}
                    </summary>
                    <div className="mt-1 space-y-0.5">
                      {tradeRows.map(row => (
                        <div key={row.tradeId} className="flex items-center gap-2 flex-wrap">
                          <span className="text-gray-500">[{row.tradeId}]</span>
                          <span className={row.direction === 'short' ? 'text-red-400' : 'text-emerald-400'}>
                            {(row.direction ?? '?').toUpperCase()}
                          </span>
                          <span className="text-gray-400">#{row.openCandle} @ {row.openPrice}</span>
                          <span className="text-gray-600">→</span>
                          {row.pips !== undefined ? (
                            <>
                              <span className="text-gray-400">#{row.closeCandle} @ {row.closePrice}</span>
                              <span className={row.pips >= 0 ? 'text-emerald-400' : 'text-red-400'}>
                                {row.pips >= 0 ? '+' : ''}{row.pips.toFixed(1)} pips
                              </span>
                            </>
                          ) : (
                            <span className="text-amber-400">offen</span>
                          )}
                          {row.note && <span className="text-gray-600 italic truncate">— {row.note}</span>}
                        </div>
                      ))}
                    </div>
                  </details>
                )}

                {lastStepResult ? (
                  <div className="space-y-1 border-t border-gray-800 pt-2">
                    <span className="text-white">Letzter Step</span>
                    <details className="text-[11px] text-white font-mono bg-gray-900/60 border border-gray-800 rounded p-2" open>
                      <summary
                        className="cursor-pointer select-none text-gray-400 hover:text-white"
                        title="Die geparste AA-Entscheidung des letzten Step/Run-Ticks — inkl. Retry-Info, falls die Antwort erst nach Korrektur valides JSON war"
                      >
                        Decision
                        {(lastStepResult.decisionRetries ?? 0) > 0 && ` — ${lastStepResult.decisionRetries}× retried`}
                        {lastStepResult.decisionValid === false && ' — INVALID after all retries'}
                      </summary>
                      {lastStepResult.decision ? (
                        <JsonViewer data={lastStepResult.decision} defaultExpandLevel={2} className="mt-1" />
                      ) : (
                        <p className="mt-1 text-gray-500">(invalid — no JSON could be parsed)</p>
                      )}
                      {(lastStepResult.decisionDiscarded?.length ?? 0) > 0 && (
                        <div className="mt-1.5 pt-1.5 border-t border-gray-800 space-y-1">
                          <div className="text-gray-500">Discarded attempts:</div>
                          {lastStepResult.decisionDiscarded!.map((text, i) => (
                            <pre key={i} className="whitespace-pre-wrap break-all text-red-300/80 bg-gray-950/60 rounded px-1 py-0.5 mb-1">
                              {text}
                            </pre>
                          ))}
                        </div>
                      )}
                    </details>
                    {lastStepResult.scriptInput && (
                      <details className="text-[11px] text-white font-mono bg-gray-900/60 border border-gray-800 rounded p-2">
                        <summary
                          className="cursor-pointer select-none text-gray-400 hover:text-white"
                          title="Das exakte 'input'-JSON, das an das BA Decision Script übergeben wurde — backend-erzeugt, nicht editierbar"
                        >
                          Script Input
                        </summary>
                        <JsonViewer data={lastStepResult.scriptInput} defaultExpandLevel={2} className="mt-1" />
                      </details>
                    )}
                    {lastStepResult.scriptResult && (
                      <details className="text-[11px] text-white font-mono bg-gray-900/60 border border-gray-800 rounded p-2">
                        <summary className="cursor-pointer select-none text-gray-400 hover:text-white">
                          Script Result
                        </summary>
                        <JsonViewer data={lastStepResult.scriptResult} defaultExpandLevel={2} className="mt-1" />
                      </details>
                    )}
                    {lastStepResult.scriptError && (
                      <pre className="whitespace-pre-wrap break-words text-[11px] text-red-400 bg-gray-900/60 border border-red-900/50 rounded p-2">
                        Script Error: {lastStepResult.scriptError}
                      </pre>
                    )}
                  </div>
                ) : (
                  <p className="text-white italic text-xs border-t border-gray-800 pt-2">
                    Noch kein Step gelaufen — Decision/Script Input erscheinen hier nach dem ersten Step/Run.
                  </p>
                )}
              </>
            ) : (
              <>
                <p className="text-white">
                  Exakte Vorschau dessen, was der Agent bei der nächsten Chat-Nachricht als Kontext bekäme — über
                  denselben Backend-Code wie /prompt-workbench/chat aufgebaut, nur ohne das LLM tatsächlich
                  aufzurufen. Kann also nie von der Realität abweichen.
                </p>
                {candles.length === 0 ? (
                  <p className="text-white italic">Keine Kerzen geladen.</p>
                ) : contextPreviewError ? (
                  <span className="text-red-400">Error: {contextPreviewError}</span>
                ) : contextPreview ? (
                  <div className="bg-gray-900/60 border border-gray-800 rounded p-2">
                    {contextPreviewLoading && <div className="text-white mb-1">Aktualisiere…</div>}
                    <JsonViewer data={contextPreview} defaultExpandLevel={1} />
                  </div>
                ) : (
                  <p className="text-white italic">{contextPreviewLoading ? 'Lädt…' : 'Kein Preview verfügbar.'}</p>
                )}
              </>
            )}
          </div>
        </section>
      </div>
    </div>
  )
}
