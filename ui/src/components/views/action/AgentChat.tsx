/**
 * AgentChat — select an agent and send free-text questions.
 *
 * Uses POST /agents/{id}/ask and shows the response in a chat-bubble style.
 */

import { useCallback, useEffect, useRef, useState, type MouseEvent as ReactMouseEvent } from 'react'
import { useDebounce } from '@/utils/useDebounce'
import {
  api,
  type AnalysisRecord,
  type CandleBar,
  type IndicatorValue,
  type MonitoringEvent,
} from '@/api/client'
import {
  ForexChart,
  type ForexChartHandle,
  type ForexChartMarker,
  type ForexChartOscillator,
  type ForexChartOverlayLine,
} from '@/components/charts/ForexChart'
import { useAgents } from '@/hooks/useAgents'

import { Bot, Check, ChevronDown, ChevronRight, Copy, Play, RefreshCcw, Send, User } from 'lucide-react'

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

interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  agentId?: string
  timestamp: string
  title?: string
  runId?: string
}

interface InspectRun {
  run_id: string
  agent_id: string
  trigger: string
  source: string
  built_user_message: string
  final_response: string
  effective_system_prompt?: string | null
  total_tokens: number
  elapsed_ms: number
  snapshot?: Record<string, unknown> | null
  validation_errors: string[]
  events: MonitoringEvent[]
}

function now(): string {
  return new Date().toISOString().replace('T', ' ').substring(11, 19) + ' UTC'
}

function findNearestCandleTimestamp(candles: CandleBar[], targetTimestamp: string): string | null {
  if (!candles.length) return null
  const targetMs = new Date(targetTimestamp).getTime()
  if (!Number.isFinite(targetMs)) return candles[0]?.timestamp ?? null
  const nearest = [...candles].sort(
    (left, right) =>
      Math.abs(new Date(left.timestamp).getTime() - targetMs) -
      Math.abs(new Date(right.timestamp).getTime() - targetMs),
  )[0]
  return nearest?.timestamp ?? null
}

function formatAssistantContent(raw: string): string {
  const tryParseJson = (text: string): unknown | null => {
    const t = text.trim()
    if (!t) return null
    try {
      return JSON.parse(t)
    } catch {
      // Try fenced code block
      const fenced = t.match(/```(?:json)?\s*([\s\S]*?)\s*```/i)
      if (fenced?.[1]) {
        try {
          return JSON.parse(fenced[1].trim())
        } catch {
          // continue
        }
      }
      // Try extracting first JSON object from surrounding text
      const first = t.indexOf('{')
      const last = t.lastIndexOf('}')
      if (first >= 0 && last > first) {
        try {
          return JSON.parse(t.slice(first, last + 1))
        } catch {
          return null
        }
      }
      return null
    }
  }

  const formatValue = (v: unknown, indent = 0): string => {
    const pad = '  '.repeat(indent)
    if (v === null || v === undefined) return `${v}`
    if (typeof v === 'string' || typeof v === 'number' || typeof v === 'boolean') return String(v)
    if (Array.isArray(v)) {
      if (v.length === 0) return '[]'
      return v
        .map(item => `${pad}- ${formatValue(item, indent + 1)}`)
        .join('\n')
    }
    if (typeof v === 'object') {
      const entries = Object.entries(v as Record<string, unknown>)
      if (entries.length === 0) return '{}'
      return entries
        .map(([k, val]) => {
          if (val && typeof val === 'object') {
            return `${pad}${k}:\n${formatValue(val, indent + 1)}`
          }
          return `${pad}${k}: ${formatValue(val, indent + 1)}`
        })
        .join('\n')
    }
    return String(v)
  }

  const parsed = tryParseJson(raw)
  if (parsed !== null) {
    if (typeof parsed === 'string') {
      const nested = tryParseJson(parsed)
      if (nested !== null) return formatValue(nested)
      return parsed
    }
    return formatValue(parsed)
  }

  if (raw.includes('\\n')) {
    return raw
      .replace(/\\n/g, '\n')
      .replace(/\\"/g, '"')
      .replace(/\\\\/g, '\\')
  }
  return raw
}

function toPrettyText(value: unknown): string {
  if (typeof value === 'string') return value
  try {
    return JSON.stringify(value ?? {}, null, 2)
  } catch {
    return String(value)
  }
}

function downloadTextFile(filename: string, content: string) {
  const blob = new Blob([content], { type: 'text/markdown;charset=utf-8' })
  const href = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = href
  anchor.download = filename
  anchor.click()
  URL.revokeObjectURL(href)
}

export function AgentChat() {
  const { agents, loading: agentsLoading } = useAgents()
  const inputRef = useRef<HTMLTextAreaElement | null>(null)
  const [selectedAgent, setSelectedAgent] = useState<string>('')
  const [input, setInput] = useState('')
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [sending, setSending] = useState(false)
  const [timeout, setTimeout_] = useState(120)
  const [collapsedMessages, setCollapsedMessages] = useState<Set<string>>(new Set())
  const [selectedForHistory, setSelectedForHistory] = useState<Set<string>>(new Set())
  const [chartRange, setChartRange] = useState(100)
  const [candles, setCandles] = useState<CandleBar[]>([])
  const [emaFastValues, setEmaFastValues] = useState<IndicatorValue[]>([])
  const [emaSlowValues, setEmaSlowValues] = useState<IndicatorValue[]>([])
  const [rsiValues, setRsiValues] = useState<IndicatorValue[]>([])
  const [atrValues, setAtrValues] = useState<IndicatorValue[]>([])
  const [candlesLoading, setCandlesLoading] = useState(false)
  const [candlesError, setCandlesError] = useState<string | null>(null)
  const [chartTimeframe, setChartTimeframe] = useState<'M5' | 'M15' | 'M30' | 'H1'>('M5')
  const [showAnalyses, setShowAnalyses] = useState(true)
  const [analysisRecords, setAnalysisRecords] = useState<AnalysisRecord[]>([])
  const [selectedAnalysis, setSelectedAnalysis] = useState<AnalysisRecord | null>(null)
  const [copiedMessageId, setCopiedMessageId] = useState<string | null>(null)
  const [runDetails, setRunDetails] = useState<Record<string, InspectRun>>({})
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null)
  const [inspectorTab, setInspectorTab] = useState<'overview' | 'snapshot' | 'llm' | 'tools' | 'runtime'>('overview')

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
  const chartRef = useRef<ForexChartHandle | null>(null)
  const splitRef = useRef<HTMLDivElement | null>(null)
  const isDragging = useRef(false)
  const [leftWidthPct, setLeftWidthPct] = useState(50)

  useEffect(() => {
    const onMouseMove = (e: MouseEvent) => {
      if (!isDragging.current || !splitRef.current) return
      const rect = splitRef.current.getBoundingClientRect()
      const pct = ((e.clientX - rect.left) / rect.width) * 100
      setLeftWidthPct(Math.min(80, Math.max(20, pct)))
    }
    const onMouseUp = () => { isDragging.current = false }
    window.addEventListener('mousemove', onMouseMove)
    window.addEventListener('mouseup', onMouseUp)
    return () => {
      window.removeEventListener('mousemove', onMouseMove)
      window.removeEventListener('mouseup', onMouseUp)
    }
  }, [])
  // Monitoring stream for candle events kept for other uses; auto-refresh removed.
  // const { events: candleEvents } = useMonitoringStream({ filter: ['m5_candle_queued'] })


  const refreshCandles = useCallback(async () => {
    if (!selectedAgent || !selectedAgent.includes('-AA-')) {
      setCandles([])
      setCandlesError(null)
      setCandlesLoading(false)
      return
    }
    const fetchCount = 200
    setCandlesLoading(true)
    setCandlesError(null)
    try {
      const data = await api.getAgentCandles(selectedAgent, chartTimeframe, fetchCount)
      setCandles(data)
    } catch (err) {
      setCandlesError(String(err))
    } finally {
      setCandlesLoading(false)
    }
  }, [selectedAgent, chartTimeframe])

  useEffect(() => {
    void refreshCandles()
  }, [refreshCandles])

  // Auto-refresh removed — use the Refresh button to manually reload candles.

  useEffect(() => {
    if (!selectedAgent || !selectedAgent.includes('-AA-') || !showAnalyses) {
      setAnalysisRecords([])
      return
    }
    let cancelled = false
    async function loadAnalyses() {
      try {
        const data = await api.getAnalyses({ agent_id: selectedAgent, limit: 300 })
        if (!cancelled) setAnalysisRecords(data)
      } catch {
        if (!cancelled) setAnalysisRecords([])
      }
    }
    void loadAnalyses()
    return () => {
      cancelled = true
    }
  }, [selectedAgent, showAnalyses])

  const analysisMarkers: ForexChartMarker[] = showAnalyses
    ? ((analysisRecords
        .map(record => {
          const markerTimestamp = findNearestCandleTimestamp(candles, record.decided_at)
          if (!markerTimestamp) return null
          const decision = String(record.decision ?? '').toUpperCase()
          const label = decision === 'BIAS_LONG' ? 'U' : decision === 'BIAS_SHORT' ? 'D' : 'N'
          return {
            timestamp: markerTimestamp,
            position: 'inBar',
            shape: 'square',
            color: '#fb923c',
            text: label,
            payload: record,
          } satisfies ForexChartMarker
        })
        .filter(Boolean)) as ForexChartMarker[])
    : []

  useEffect(() => {
    if (!showEma || !selectedAgent) { setEmaFastValues([]); setEmaSlowValues([]); return }
    const history = Math.min(500, candles.length + Math.max(dEmaFastPeriod, dEmaSlowPeriod))
    Promise.all([
      api.calculateIndicator({ indicator: 'EMA', period: dEmaFastPeriod, timeframe: dEmaTf, history, agent_id: selectedAgent }),
      api.calculateIndicator({ indicator: 'EMA', period: dEmaSlowPeriod, timeframe: dEmaTf, history, agent_id: selectedAgent }),
    ]).then(([fast, slow]) => { setEmaFastValues(fast.values ?? []); setEmaSlowValues(slow.values ?? []) })
      .catch(() => { setEmaFastValues([]); setEmaSlowValues([]) })
  }, [showEma, selectedAgent, dEmaFastPeriod, dEmaSlowPeriod, dEmaTf, candles.length])

  useEffect(() => {
    if (!showRsi || !selectedAgent) { setRsiValues([]); return }
    api.calculateIndicator({ indicator: 'RSI', period: dRsiPeriod, timeframe: dRsiTf, history: Math.min(500, candles.length + dRsiPeriod), agent_id: selectedAgent })
      .then(r => setRsiValues(r.values ?? []))
      .catch(() => setRsiValues([]))
  }, [showRsi, selectedAgent, dRsiPeriod, dRsiTf, candles.length])

  useEffect(() => {
    if (!showAtr || !selectedAgent) { setAtrValues([]); return }
    api.calculateIndicator({ indicator: 'ATR', period: dAtrPeriod, timeframe: dAtrTf, history: Math.min(500, candles.length + dAtrPeriod), agent_id: selectedAgent })
      .then(r => setAtrValues(r.values ?? []))
      .catch(() => setAtrValues([]))
  }, [showAtr, selectedAgent, dAtrPeriod, dAtrTf, candles.length])

  const overlayLines: ForexChartOverlayLine[] = showEma ? [
    { key: 'ema_fast', label: `EMA ${emaFastPeriod} ${emaTf}`, color: '#facc15', values: emaFastValues },
    { key: 'ema_slow', label: `EMA ${emaSlowPeriod} ${emaTf}`, color: '#60a5fa', values: emaSlowValues },
  ] : []
  const oscillators: ForexChartOscillator[] = [
    ...(showRsi ? [{ key: 'rsi_primary', label: `RSI ${rsiPeriod} ${rsiTf}`, color: '#a78bfa', precision: 1, values: rsiValues }] : []),
    ...(showAtr ? [{ key: 'atr_primary', label: `ATR ${atrPeriod} ${atrTf}`, color: '#94a3b8', precision: 5, values: atrValues }] : []),
  ]

  const tfOptions = ['M5', 'M15', 'M30', 'H1', 'H4', 'D1']
  const inputCls = 'w-10 bg-gray-800 border border-gray-600 rounded px-1 text-gray-200 text-xs text-center'
  const selectCls = 'bg-gray-800 border border-gray-600 rounded px-1 text-gray-200 text-xs'
  const indicatorControls = selectedAgent && selectedAgent.includes('-AA-') ? (
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
          {tfOptions.map(tf => <option key={tf}>{tf}</option>)}
        </select>
      </span>
      <span className="flex items-center gap-1.5">
        <label className="flex items-center gap-1 cursor-pointer select-none">
          <input type="checkbox" checked={showRsi} onChange={e => setShowRsi(e.target.checked)} className="accent-violet-400" />
          <span className={showRsi ? 'text-violet-400' : ''}>RSI</span>
        </label>
        <input type="number" min={1} max={500} value={rsiPeriod} onChange={e => setRsiPeriod(Math.max(1, Number(e.target.value)))} className={inputCls} title="Period" />
        <select value={rsiTf} onChange={e => setRsiTf(e.target.value)} className={selectCls}>
          {tfOptions.map(tf => <option key={tf}>{tf}</option>)}
        </select>
      </span>
      <span className="flex items-center gap-1.5">
        <label className="flex items-center gap-1 cursor-pointer select-none">
          <input type="checkbox" checked={showAtr} onChange={e => setShowAtr(e.target.checked)} className="accent-slate-400" />
          <span className={showAtr ? 'text-slate-300' : ''}>ATR</span>
        </label>
        <input type="number" min={1} max={500} value={atrPeriod} onChange={e => setAtrPeriod(Math.max(1, Number(e.target.value)))} className={inputCls} title="Period" />
        <select value={atrTf} onChange={e => setAtrTf(e.target.value)} className={selectCls}>
          {tfOptions.map(tf => <option key={tf}>{tf}</option>)}
        </select>
      </span>
    </>
  ) : null

  const selectedRun = selectedRunId ? runDetails[selectedRunId] ?? null : null
  const llmRequestEvents = selectedRun?.events.filter(event => event.event_type === 'llm_request') ?? []
  const llmResponseEvents = selectedRun?.events.filter(event => event.event_type === 'llm_response') ?? []
  const toolEvents = selectedRun?.events.filter(event => event.event_type.startsWith('tool_call_')) ?? []
  const runtimeEvents = selectedRun?.events ?? []

  const send = async () => {
    if (!selectedAgent || !input.trim() || sending) return

    const question = input.trim()
    setInput('')
    setSending(true)

    const userMsg: ChatMessage = {
      id: `u-${Date.now()}`,
      role: 'user',
      content: question,
      timestamp: now(),
    }
    setMessages(prev => [...prev, userMsg])

    try {
      const history = messages
        .filter(m => selectedForHistory.has(m.id))
        .map(m => ({ role: m.role, content: m.content }))
      const resp = await api.askAgent(selectedAgent, question, timeout, history.length ? history : undefined)
      const assistantMsg: ChatMessage = {
        id: `a-${Date.now()}`,
        role: 'assistant',
        content: resp.response ? formatAssistantContent(resp.response) : '(empty response)',
        agentId: resp.agent_id,
        timestamp: now(),
      }
      setMessages(prev => [...prev, assistantMsg])
    } catch (err) {
      const errMsg: ChatMessage = {
        id: `e-${Date.now()}`,
        role: 'assistant',
        content: `Error: ${String(err)}`,
        agentId: selectedAgent,
        timestamp: now(),
      }
      setMessages(prev => [...prev, errMsg])
    } finally {
      setSending(false)
      // Keep keyboard flow smooth after response.
      inputRef.current?.focus()
    }
  }

  const executeAgent = async () => {
    if (!selectedAgent || sending) return

    const rawInput = input
    const executeLabel = rawInput.trim()
      ? rawInput.trim()
      : `Execute standard kickoff for ${selectedAgent}`

    setInput('')
    setSending(true)

    const userMsg: ChatMessage = {
      id: `x-u-${Date.now()}`,
      role: 'user',
      title: 'Execute',
      content: executeLabel,
      timestamp: now(),
    }
    setMessages(prev => [...prev, userMsg])

    try {
      const response = await api.executeAgent(selectedAgent, { input_text: rawInput })
      const inspectRun: InspectRun = {
        ...response,
        effective_system_prompt: response.effective_system_prompt ?? null,
        snapshot: response.snapshot ?? null,
      }
      setRunDetails(prev => ({ ...prev, [response.run_id]: inspectRun }))
      setSelectedRunId(response.run_id)
      setInspectorTab('overview')

      const builtInputMessage: ChatMessage = {
        id: `x-bi-${Date.now()}`,
        role: 'assistant',
        title: 'Built Input',
        content: response.built_user_message || '(empty input)',
        agentId: response.agent_id,
        timestamp: now(),
        runId: response.run_id,
      }
      const resultText = response.final_response?.trim()
        ? formatAssistantContent(response.final_response)
        : (response.validation_errors.length > 0
          ? `Validation blocked execution:\n${response.validation_errors.join('\n')}`
          : '(empty response)')
      const finalMessage: ChatMessage = {
        id: `x-a-${Date.now()}`,
        role: 'assistant',
        title: 'Execute Result',
        content: resultText,
        agentId: response.agent_id,
        timestamp: now(),
        runId: response.run_id,
      }
      setMessages(prev => [...prev, builtInputMessage, finalMessage])
    } catch (err) {
      const errMsg: ChatMessage = {
        id: `x-e-${Date.now()}`,
        role: 'assistant',
        title: 'Execute Error',
        content: `Error: ${String(err)}`,
        agentId: selectedAgent,
        timestamp: now(),
      }
      setMessages(prev => [...prev, errMsg])
    } finally {
      setSending(false)
      inputRef.current?.focus()
    }
  }

  const exportChatMarkdown = () => {
    const lines: string[] = [
      '# Agent Chat Export',
      '',
      `- Agent: ${selectedAgent || '(none selected)'}`,
      `- Exported At: ${new Date().toISOString()}`,
      '',
    ]
    for (const msg of messages) {
      lines.push(`## ${msg.role === 'user' ? 'User' : 'Assistant'} · ${msg.timestamp}`)
      if (msg.agentId) lines.push(`Agent: ${msg.agentId}`)
      if (msg.title) lines.push(`Title: ${msg.title}`)
      if (msg.runId) lines.push(`Run: ${msg.runId}`)
      lines.push('')
      lines.push('```text')
      lines.push(msg.content)
      lines.push('```')
      lines.push('')
    }
    downloadTextFile('agent-chat-export.md', lines.join('\n'))
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      send()
    }
  }

  const copyMessage = async (id: string, content: string) => {
    try {
      await navigator.clipboard.writeText(content)
      setCopiedMessageId(id)
      window.setTimeout(() => setCopiedMessageId(current => (current === id ? null : current)), 1200)
    } catch {
      // Ignore clipboard errors silently.
    }
  }

  return (
    <div className="flex flex-col h-full">
      <div ref={splitRef} className="flex-1 min-h-0 flex select-none">
        {/* Left column: chat controls + chat */}
        <section style={{ width: `${leftWidthPct}%` }} className="flex flex-col min-h-0 flex-shrink-0 border-r border-gray-700">
          <div className="px-4 py-2 bg-gray-900 border-b border-gray-700 flex-shrink-0 space-y-2">
            <div className="flex items-center gap-3">
              <label className="text-xs text-gray-400 flex-shrink-0">Agent:</label>
              <select
                value={selectedAgent}
                onChange={e => {
                  setSelectedAgent(e.target.value)
                  setSelectedRunId(null)
                }}
                disabled={agentsLoading}
                className="flex-1 max-w-xs bg-gray-800 text-gray-200 text-sm rounded px-2 py-1 border border-gray-600 focus:outline-none focus:border-emerald-500"
              >
                <option value="">— select agent —</option>
                {agents.map(a => (
                  <option key={a.agent_id} value={a.agent_id}>{a.agent_id}</option>
                ))}
              </select>

              <label className="text-xs text-gray-400 flex-shrink-0 ml-4">Timeout (s):</label>
              <input
                type="number"
                min={5}
                max={300}
                value={timeout}
                onChange={e => setTimeout_(Number(e.target.value))}
                className="w-16 bg-gray-800 text-gray-200 text-sm rounded px-2 py-1 border border-gray-600 focus:outline-none focus:border-emerald-500"
              />

              <button
                onClick={() => {
                  setMessages([])
                  setRunDetails({})
                  setSelectedRunId(null)
                }}
                className="ml-auto text-xs px-2.5 py-1 rounded border border-red-800 bg-red-900/30 text-red-300 hover:bg-red-900/60 transition-colors"
              >
                Clear chat
              </button>
              <button
                onClick={exportChatMarkdown}
                disabled={messages.length === 0}
                className="text-xs px-2.5 py-1 rounded border border-blue-700 bg-blue-900/30 text-blue-300 hover:bg-blue-900/60 transition-colors disabled:opacity-40"
              >
                Export .md
              </button>
            </div>

          </div>

          <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
            {messages.length === 0 && (
                <div className="text-center text-gray-600 mt-16 text-sm">
                  Select an agent and send a question.<br />
                  <span className="text-xs text-gray-700">Enter to send, Shift+Enter for newline</span>
                </div>
            )}
            {messages.map(msg => {
              const collapsed = collapsedMessages.has(msg.id)
              const inHistory = selectedForHistory.has(msg.id)
              return (
                <div key={msg.id} className={`flex gap-3 ${msg.role === 'user' ? 'flex-row-reverse' : ''}`}>
                  <div className={`flex-shrink-0 w-7 h-7 rounded-full flex items-center justify-center mt-0.5 ${
                    msg.role === 'user' ? 'bg-emerald-800' : 'bg-blue-900'
                  }`}>
                    {msg.role === 'user'
                      ? <User className="w-4 h-4 text-emerald-300" />
                      : <Bot className="w-4 h-4 text-blue-300" />}
                  </div>
                  <div className={`max-w-2xl min-w-0 flex-1 ${msg.role === 'user' ? 'items-end' : 'items-start'} flex flex-col gap-1`}>
                    {/* Header row */}
                    <div
                      className="flex items-center gap-2 text-xs text-gray-500 cursor-pointer select-none"
                      onClick={() => setCollapsedMessages(prev => {
                        const next = new Set(prev)
                        next.has(msg.id) ? next.delete(msg.id) : next.add(msg.id)
                        return next
                      })}
                    >
                      {collapsed
                        ? <ChevronRight className="w-3 h-3 text-gray-600" />
                        : <ChevronDown className="w-3 h-3 text-gray-600" />}
                      {msg.role === 'assistant' && msg.agentId && (
                        <span className="text-blue-400">{msg.agentId}</span>
                      )}
                      <span>{msg.timestamp}</span>
                      <button
                        onClick={e => { e.stopPropagation(); void copyMessage(msg.id, msg.content) }}
                        title="Copy message text"
                        className="inline-flex items-center gap-1 text-gray-500 hover:text-gray-200"
                      >
                        <Copy className="w-3.5 h-3.5" />
                        <span>{copiedMessageId === msg.id ? 'Copied' : 'Copy'}</span>
                      </button>
                      <label
                        title="Include in history"
                        className="flex items-center gap-1 ml-1 cursor-pointer"
                        onClick={e => e.stopPropagation()}
                      >
                        <input
                          type="checkbox"
                          checked={inHistory}
                          onChange={() => setSelectedForHistory(prev => {
                            const next = new Set(prev)
                            next.has(msg.id) ? next.delete(msg.id) : next.add(msg.id)
                            return next
                          })}
                          className="accent-emerald-500 w-3 h-3"
                        />
                        <span className={inHistory ? 'text-emerald-400' : ''}>History</span>
                      </label>
                      {msg.runId && (
                        <button
                          onClick={e => { e.stopPropagation(); setSelectedRunId(msg.runId ?? null) }}
                          className="text-gray-600 hover:text-gray-400"
                        >
                          Inspect
                        </button>
                      )}
                    </div>
                    {/* Body */}
                    {!collapsed && (
                      <div className={`rounded-lg px-3 py-2 text-sm whitespace-pre-wrap break-words w-full ${
                        msg.role === 'user'
                          ? 'bg-emerald-900/50 text-emerald-100'
                          : 'bg-gray-800 text-gray-200'
                      } ${
                        msg.runId && selectedRunId === msg.runId ? 'ring-1 ring-emerald-500/70' : ''
                      }`}>
                        {msg.title && (
                          <div className="text-[11px] uppercase tracking-wide text-gray-400 mb-1">
                            {msg.title}
                          </div>
                        )}
                        {msg.content}
                      </div>
                    )}
                  </div>
                </div>
              )
            })}

            {sending && (
              <div className="flex gap-3">
                <div className="flex-shrink-0 w-7 h-7 rounded-full bg-blue-900 flex items-center justify-center">
                  <Bot className="w-4 h-4 text-blue-300" />
                </div>
                <div className="bg-gray-800 rounded-lg px-3 py-2 text-sm text-gray-400 animate-pulse">
                  Waiting for {selectedAgent}…
                </div>
              </div>
            )}
          </div>

          <div className="flex-shrink-0 px-4 py-3 bg-gray-900 border-t border-gray-700">
            <div className="flex gap-2 items-end">
              <textarea
                ref={inputRef}
                value={input}
                onChange={e => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder={
                  selectedAgent
                    ? (selectedAgent.includes('-BA-')
                      ? `Paste analysis JSON for ${selectedAgent} and click Execute…`
                      : `Ask ${selectedAgent}…`)
                    : 'Select an agent first'
                }
                disabled={!selectedAgent}
                rows={3}
                className="flex-1 resize-none bg-gray-800 text-gray-200 text-sm rounded px-3 py-2 border border-gray-600 focus:outline-none focus:border-emerald-500 placeholder-gray-600"
              />
              <div className="flex flex-col gap-2 flex-shrink-0">
                <button
                  onClick={send}
                  disabled={!selectedAgent || !input.trim() || sending}
                  className="flex items-center gap-1.5 px-4 py-2 bg-emerald-700 hover:bg-emerald-600 disabled:bg-gray-700 disabled:text-gray-500 text-white text-sm rounded transition-colors"
                >
                  <Send className="w-4 h-4" />
                  Send
                </button>
                <button
                  onClick={() => void executeAgent()}
                  disabled={!selectedAgent || sending}
                  className="flex items-center gap-1.5 px-4 py-2 bg-violet-700 hover:bg-violet-600 disabled:bg-gray-700 disabled:text-gray-500 text-white text-sm rounded transition-colors"
                >
                  <Play className="w-4 h-4" />
                  Analysis
                </button>
              </div>
            </div>
            <p className="text-xs text-gray-600 mt-1">
              Enter sends chat. Execute runs the selected agent in inspect mode.
            </p>
          </div>
        </section>

        {/* Drag handle */}
        <div
          onMouseDown={(e: ReactMouseEvent) => { isDragging.current = true; e.preventDefault() }}
          className="w-1 flex-shrink-0 bg-gray-700 hover:bg-emerald-500 active:bg-emerald-400 cursor-col-resize transition-colors"
        />
        {/* Right column: agent-dependent extra info */}
        <aside className="flex flex-col min-h-0 bg-gray-950 flex-1 min-w-0">
          <div className="px-4 py-2 border-b border-gray-700 bg-gray-900">
            <h3 className="text-sm text-gray-200 font-medium">Agent Context</h3>
          </div>
          <div className="flex-1 min-h-0 p-4 overflow-auto">
            {!selectedAgent && (
              <p className="text-sm text-gray-500">Select an agent to see additional context.</p>
            )}
            {selectedAgent && (
              <div className="h-full min-h-[280px] flex flex-col gap-3">
                {selectedAgent.includes('-AA-') ? (
                  <>
                    <div className="flex items-center gap-2 flex-wrap">
                      <button
                        onClick={() => void refreshCandles()}
                        disabled={candlesLoading}
                        className="flex items-center gap-1 px-2 py-0.5 rounded border border-gray-700 bg-gray-900 text-gray-400 hover:text-white text-xs flex-shrink-0"
                        title="Refresh candles"
                      >
                        <RefreshCcw className={`w-3 h-3 ${candlesLoading ? 'animate-spin' : ''}`} />
                        {candlesLoading ? 'Loading…' : 'Refresh'}
                      </button>
                      <button
                        onClick={() => chartRef.current?.resetView()}
                        className="px-2 py-0.5 rounded border border-gray-700 bg-gray-900 text-gray-400 hover:text-gray-200 text-xs flex-shrink-0"
                      >
                        Reset
                      </button>
                      {(['M5', 'M15', 'M30', 'H1'] as const).map(tf => (
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
                      {[20, 50, 100].map(n => (
                        <button
                          key={n}
                          onClick={() => setChartRange(n)}
                          className={[
                            'px-2 py-0.5 rounded border text-xs',
                            chartRange === n
                              ? 'border-emerald-500 bg-emerald-900/30 text-emerald-300'
                              : 'border-gray-700 bg-gray-900 text-gray-400 hover:text-gray-200',
                          ].join(' ')}
                        >
                          {n}
                        </button>
                      ))}
                      <label className="ml-auto inline-flex items-center gap-1 text-xs text-gray-400 cursor-pointer select-none">
                        <input
                          type="checkbox"
                          checked={showAnalyses}
                          onChange={e => setShowAnalyses(e.target.checked)}
                          className="rounded border-gray-600 bg-gray-900 text-emerald-500"
                        />
                        Show the Analyses
                      </label>
                    </div>
                    {candlesError && <p className="text-sm text-red-400">Error: {candlesError}</p>}
                    <div className="h-1/2 min-h-[260px]">
                      {candles.length > 0 ? (
                        <ForexChart
                          ref={chartRef}
                          candles={candles}
                          markers={analysisMarkers}
                          overlayLines={overlayLines}
                          oscillators={oscillators}
                          ranges={[]}
                          range={chartRange}
                          indicatorControls={indicatorControls}
                          onMarkerSelect={marker => {
                            if (marker.payload) setSelectedAnalysis(marker.payload as AnalysisRecord)
                          }}
                        />
                      ) : (
                        <div className="text-xs text-gray-500 border border-gray-700 rounded p-3 bg-gray-900">
                          No candle data available.
                        </div>
                      )}
                    </div>
                  </>
                ) : (
                  <div className="rounded border border-gray-800 bg-gray-900/40 p-4 text-sm text-gray-500">
                    Execute inspection details for this agent appear below. This agent type has no chart view.
                  </div>
                )}
                <div className="flex-1 min-h-0 border border-gray-800 rounded bg-gray-900/40 flex flex-col overflow-hidden">
                  <div className="px-3 py-2 border-b border-gray-800 flex flex-wrap items-center gap-2">
                    {([
                      ['overview', 'Overview'],
                      ['snapshot', 'Snapshot'],
                      ['llm', 'LLM'],
                      ['tools', 'Tools'],
                      ['runtime', 'Runtime'],
                    ] as const).map(([key, label]) => (
                      <button
                        key={key}
                        onClick={() => setInspectorTab(key)}
                        className={[
                          'px-2.5 py-1 rounded border text-xs',
                          inspectorTab === key
                            ? 'border-emerald-500 bg-emerald-900/30 text-emerald-300'
                            : 'border-gray-700 bg-gray-900 text-gray-400 hover:text-gray-200',
                        ].join(' ')}
                      >
                        {label}
                      </button>
                    ))}
                    {selectedRun && (
                      <span className="ml-auto text-xs text-gray-500">
                        {selectedRun.agent_id} · {selectedRun.trigger} · {selectedRun.elapsed_ms.toFixed(1)} ms
                      </span>
                    )}
                  </div>
                  <div className="flex-1 min-h-0 overflow-auto p-3">
                    {!selectedRun && (
                      <p className="text-sm text-gray-500">
                        Run an Execute cycle and select its chat entry to inspect snapshot, LLM, tools, and runtime details.
                      </p>
                    )}
                    {selectedRun && inspectorTab === 'overview' && (
                      <div className="space-y-3 text-xs">
                        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                          <div className="rounded border border-gray-800 bg-gray-950/70 p-3">
                            <div className="text-gray-500">Trigger</div>
                            <div className="text-gray-100 mt-1">{selectedRun.trigger}</div>
                          </div>
                          <div className="rounded border border-gray-800 bg-gray-950/70 p-3">
                            <div className="text-gray-500">Elapsed</div>
                            <div className="text-gray-100 mt-1">{selectedRun.elapsed_ms.toFixed(1)} ms</div>
                          </div>
                          <div className="rounded border border-gray-800 bg-gray-950/70 p-3">
                            <div className="text-gray-500">Tokens</div>
                            <div className="text-gray-100 mt-1">{selectedRun.total_tokens}</div>
                          </div>
                          <div className="rounded border border-gray-800 bg-gray-950/70 p-3">
                            <div className="text-gray-500">Validation</div>
                            <div className="text-gray-100 mt-1">
                              {selectedRun.validation_errors.length === 0 ? 'passed' : 'blocked'}
                            </div>
                          </div>
                        </div>
                        <div className="rounded border border-gray-800 bg-gray-950/70 p-3">
                          <div className="text-gray-500 mb-2">Built Input</div>
                          <pre className="whitespace-pre-wrap break-words text-xs text-gray-300 leading-5">
                            {selectedRun.built_user_message}
                          </pre>
                        </div>
                        <div className="rounded border border-gray-800 bg-gray-950/70 p-3">
                          <div className="text-gray-500 mb-2">Final Output</div>
                          <pre className="whitespace-pre-wrap break-words text-xs text-gray-300 leading-5">
                            {selectedRun.final_response || '(empty response)'}
                          </pre>
                        </div>
                      </div>
                    )}
                    {selectedRun && inspectorTab === 'snapshot' && (
                      <div className="space-y-3 text-xs">
                        {selectedRun.snapshot ? (
                          <pre className="whitespace-pre-wrap break-words text-gray-300 leading-5">
                            {JSON.stringify(selectedRun.snapshot, null, 2)}
                          </pre>
                        ) : (
                          <p className="text-gray-500">No snapshot was produced for this run.</p>
                        )}
                        {selectedRun.validation_errors.length > 0 && (
                          <div className="rounded border border-amber-700/50 bg-amber-900/20 p-3 text-amber-300">
                            {selectedRun.validation_errors.join('\n')}
                          </div>
                        )}
                      </div>
                    )}
                    {selectedRun && inspectorTab === 'llm' && (
                      <div className="space-y-3 text-xs">
                        <div className="rounded border border-gray-800 bg-gray-950/70 p-3">
                          <div className="text-gray-500 mb-2">Effective System Prompt</div>
                          <pre className="whitespace-pre-wrap break-words text-gray-300 leading-5">
                            {selectedRun.effective_system_prompt || '(not captured)'}
                          </pre>
                        </div>
                        <div className="rounded border border-gray-800 bg-gray-950/70 p-3">
                          <div className="text-gray-500 mb-2">LLM Requests</div>
                          <pre className="whitespace-pre-wrap break-words text-gray-300 leading-5">
                            {llmRequestEvents.length > 0
                              ? llmRequestEvents.map(event => toPrettyText(event.payload)).join('\n\n-----\n\n')
                              : 'No llm_request events captured.'}
                          </pre>
                        </div>
                        <div className="rounded border border-gray-800 bg-gray-950/70 p-3">
                          <div className="text-gray-500 mb-2">LLM Responses</div>
                          <pre className="whitespace-pre-wrap break-words text-gray-300 leading-5">
                            {llmResponseEvents.length > 0
                              ? llmResponseEvents.map(event => toPrettyText(event.payload)).join('\n\n-----\n\n')
                              : 'No llm_response events captured.'}
                          </pre>
                        </div>
                      </div>
                    )}
                    {selectedRun && inspectorTab === 'tools' && (
                      <pre className="whitespace-pre-wrap break-words text-xs text-gray-300 leading-5">
                        {toolEvents.length > 0
                          ? toolEvents.map(event => `[${event.event_type}] ${toPrettyText(event.payload)}`).join('\n\n-----\n\n')
                          : 'No tool events captured.'}
                      </pre>
                    )}
                    {selectedRun && inspectorTab === 'runtime' && (
                      <pre className="whitespace-pre-wrap break-words text-xs text-gray-300 leading-5">
                        {runtimeEvents.length > 0
                          ? runtimeEvents
                              .map(event => `[${event.timestamp}] ${event.event_type}\n${toPrettyText(event.payload)}`)
                              .join('\n\n-----\n\n')
                          : 'No runtime events captured.'}
                      </pre>
                    )}
                  </div>
                </div>
              </div>
            )}
          </div>
        </aside>
      </div>
      {selectedAnalysis && (
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
              <div className="rounded border border-gray-800 bg-gray-900/40 p-4 space-y-3">
                <div className="flex items-center justify-between">
                  <h4 className="text-sm font-medium text-gray-200">Decision Snapshot</h4>
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-gray-500">
                      {typeof selectedAnalysis.market_snapshot?.snapshot_schema_version === 'string'
                        ? `schema ${String(selectedAnalysis.market_snapshot.snapshot_schema_version)}`
                        : 'no schema'}
                    </span>
                    {selectedAnalysis.market_snapshot && (
                      <CopyButton getText={() => JSON.stringify(selectedAnalysis.market_snapshot, null, 2)} />
                    )}
                  </div>
                </div>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">
                  <div className="rounded border border-gray-800 bg-gray-950/70 p-3">
                    <div className="text-gray-500">Snapshot Valid</div>
                    <div className="text-gray-100 mt-1">
                      {selectedAnalysis.market_snapshot?.market_data_valid === true ? 'true' : 'false'}
                    </div>
                  </div>
                  <div className="rounded border border-gray-800 bg-gray-950/70 p-3">
                    <div className="text-gray-500">Bias Hint</div>
                    <div className="text-gray-100 mt-1">
                      {String((selectedAnalysis.market_snapshot?.features as Record<string, unknown> | undefined)?.dominant_bias_hint ?? '-')}
                    </div>
                  </div>
                  <div className="rounded border border-gray-800 bg-gray-950/70 p-3">
                    <div className="text-gray-500">Core Signals</div>
                    <div className="text-gray-100 mt-1">
                      {String((selectedAnalysis.market_snapshot?.features as Record<string, unknown> | undefined)?.core_signals_long ?? '-')}
                      {' / '}
                      {String((selectedAnalysis.market_snapshot?.features as Record<string, unknown> | undefined)?.core_signals_short ?? '-')}
                    </div>
                  </div>
                  <div className="rounded border border-gray-800 bg-gray-950/70 p-3">
                    <div className="text-gray-500">Range Bound</div>
                    <div className="text-gray-100 mt-1">
                      {String((selectedAnalysis.market_snapshot?.flags as Record<string, unknown> | undefined)?.range_bound ?? '-')}
                    </div>
                  </div>
                </div>
                <pre className="whitespace-pre-wrap break-words text-xs text-gray-300 leading-6">
                  {JSON.stringify(selectedAnalysis.market_snapshot ?? {}, null, 2)}
                </pre>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}








