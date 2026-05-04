/**
 * AgentChat — select an agent and send free-text questions.
 *
 * Uses POST /agents/{id}/ask and shows the response in a chat-bubble style.
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import { api, type AnalysisRecord, type CandleBar } from '@/api/client'
import { ForexChart, type ForexChartMarker } from '@/components/charts/ForexChart'
import { useAgents } from '@/hooks/useAgents'
import { useMonitoringStream } from '@/hooks/useMonitoringStream'
import { Send, Bot, User, Copy } from 'lucide-react'

interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  agentId?: string
  timestamp: string
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

export function AgentChat() {
  const { agents, loading: agentsLoading } = useAgents()
  const inputRef = useRef<HTMLTextAreaElement | null>(null)
  const [selectedAgent, setSelectedAgent] = useState<string>('')
  const [input, setInput] = useState('')
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [sending, setSending] = useState(false)
  const [timeout, setTimeout_] = useState(120)
  const [systemConfig, setSystemConfig] = useState<Record<string, unknown> | null>(null)
  const [instruction, setInstruction] = useState('')
  const [instructionDirty, setInstructionDirty] = useState(false)
  const [savingInstruction, setSavingInstruction] = useState(false)
  const [instructionStatus, setInstructionStatus] = useState<string | null>(null)
  const [candles, setCandles] = useState<CandleBar[]>([])
  const [candlesLoading, setCandlesLoading] = useState(false)
  const [candlesError, setCandlesError] = useState<string | null>(null)
  const [chartTimeframe, setChartTimeframe] = useState<'M5' | 'M15' | 'M30' | 'H1'>('M5')
  const [showAnalyses, setShowAnalyses] = useState(true)
  const [analysisRecords, setAnalysisRecords] = useState<AnalysisRecord[]>([])
  const [selectedAnalysis, setSelectedAnalysis] = useState<AnalysisRecord | null>(null)
  const [copiedMessageId, setCopiedMessageId] = useState<string | null>(null)
  const { events: candleEvents } = useMonitoringStream({
    filter: ['m5_candle_queued'],
    enabled: Boolean(selectedAgent && selectedAgent.includes('-AA-')),
  })
  const lastHandledCandleEventIdRef = useRef<string>('')

  const instructionForAgent = (cfg: Record<string, unknown> | null, agentId: string): string => {
    if (!cfg || !agentId) return ''
    const agentsCfg = cfg.agents as Record<string, Record<string, unknown>> | undefined
    const a = agentsCfg?.[agentId]
    return typeof a?.chat_instruction === 'string' ? a.chat_instruction : ''
  }

  const loadConfig = useCallback(async () => {
    try {
      const cfg = await api.getSystemConfig()
      setSystemConfig(cfg)
      setInstruction(instructionForAgent(cfg, selectedAgent))
      setInstructionDirty(false)
    } catch {
      // Keep chat functional even if config loading fails.
    }
  }, [selectedAgent])

  useEffect(() => {
    void loadConfig()
  }, [loadConfig])

  const refreshCandles = useCallback(async () => {
    if (!selectedAgent || !selectedAgent.includes('-AA-')) {
      setCandles([])
      setCandlesError(null)
      setCandlesLoading(false)
      return
    }
    setCandlesLoading(true)
    setCandlesError(null)
    try {
      const data = await api.getAgentCandles(selectedAgent, chartTimeframe, 100)
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

  useEffect(() => {
    if (!selectedAgent || !selectedAgent.includes('-AA-')) return
    const evt = candleEvents[candleEvents.length - 1]
    if (!evt || evt.id === lastHandledCandleEventIdRef.current) return
    lastHandledCandleEventIdRef.current = evt.id

    const pairFromAgentId = selectedAgent.split('-')[1]?.toUpperCase() ?? ''
    const eventPair = (evt.pair ?? '').toUpperCase()
    if (!pairFromAgentId || !eventPair || eventPair !== pairFromAgentId) return

    void refreshCandles()
  }, [candleEvents, refreshCandles, selectedAgent])

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

  const persistInstruction = async (showStatus = true) => {
    if (!selectedAgent || !systemConfig) return
    const next = JSON.parse(JSON.stringify(systemConfig)) as Record<string, unknown>
    const agentsCfg = (next.agents ?? {}) as Record<string, Record<string, unknown>>
    const agentCfg = (agentsCfg[selectedAgent] ?? {}) as Record<string, unknown>
    agentCfg.chat_instruction = instruction
    agentsCfg[selectedAgent] = agentCfg
    next.agents = agentsCfg

    setSavingInstruction(true)
    try {
      await api.saveSystemConfig(next)
      setSystemConfig(next)
      setInstructionDirty(false)
      if (showStatus) setInstructionStatus('Instruction saved.')
    } catch (err) {
      if (showStatus) setInstructionStatus(`Save failed: ${String(err)}`)
    } finally {
      setSavingInstruction(false)
    }
  }

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
      if (instructionDirty) {
        await persistInstruction(false)
      }
      const combinedQuestion = instruction.trim()
        ? `Instruction:\n${instruction.trim()}\n\nQuestion:\n${question}`
        : question
      const resp = await api.askAgent(selectedAgent, combinedQuestion, timeout)
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
      <div className="flex-1 min-h-0 grid grid-cols-1 xl:grid-cols-2">
        {/* Left column: chat controls + chat */}
        <section className="flex flex-col min-h-0 border-r border-gray-700">
          <div className="px-4 py-2 bg-gray-900 border-b border-gray-700 flex-shrink-0 space-y-2">
            <div className="flex items-center gap-3">
              <label className="text-xs text-gray-400 flex-shrink-0">Agent:</label>
              <select
                value={selectedAgent}
                onChange={e => {
                  const next = e.target.value
                  setSelectedAgent(next)
                  setInstruction(instructionForAgent(systemConfig, next))
                  setInstructionDirty(false)
                  setInstructionStatus(null)
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
                onClick={() => setMessages([])}
                className="ml-auto text-xs text-gray-500 hover:text-gray-300 transition-colors"
              >
                Clear chat
              </button>
            </div>

            <div className="flex items-center gap-2">
              <label className="text-xs text-gray-400 flex-shrink-0">Instruction:</label>
              <input
                type="text"
                value={instruction}
                onChange={e => {
                  setInstruction(e.target.value)
                  setInstructionDirty(true)
                  setInstructionStatus(null)
                }}
                disabled={!selectedAgent}
                placeholder="Always answer as continuous text..."
                className="flex-1 bg-gray-800 text-gray-200 text-sm rounded px-2 py-1 border border-gray-600 focus:outline-none focus:border-emerald-500"
              />
              <button
                onClick={() => void persistInstruction(true)}
                disabled={!selectedAgent || !instructionDirty || savingInstruction}
                className="text-xs px-2 py-1 rounded bg-gray-700 text-gray-200 hover:bg-gray-600 disabled:opacity-50"
              >
                {savingInstruction ? 'Saving…' : 'Save instruction'}
              </button>
              {instructionStatus && (
                <span className="text-xs text-gray-400">{instructionStatus}</span>
              )}
            </div>
          </div>

          <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
            {messages.length === 0 && (
                <div className="text-center text-gray-600 mt-16 text-sm">
                  Select an agent and send a question.<br />
                  <span className="text-xs text-gray-700">Enter to send, Shift+Enter for newline</span>
                </div>
            )}
            {messages.map(msg => (
              <div
                key={msg.id}
                className={`flex gap-3 ${msg.role === 'user' ? 'flex-row-reverse' : ''}`}
              >
                <div className={`flex-shrink-0 w-7 h-7 rounded-full flex items-center justify-center ${
                  msg.role === 'user' ? 'bg-emerald-800' : 'bg-blue-900'
                }`}>
                  {msg.role === 'user'
                    ? <User className="w-4 h-4 text-emerald-300" />
                    : <Bot className="w-4 h-4 text-blue-300" />}
                </div>
                <div className={`max-w-2xl ${msg.role === 'user' ? 'items-end' : 'items-start'} flex flex-col gap-1`}>
                  <div className="flex items-baseline gap-2 text-xs text-gray-500">
                    {msg.role === 'assistant' && msg.agentId && (
                      <span className="text-blue-400">{msg.agentId}</span>
                    )}
                    <span>{msg.timestamp}</span>
                    <button
                      onClick={() => void copyMessage(msg.id, msg.content)}
                      title="Copy message text"
                      className="inline-flex items-center gap-1 text-gray-500 hover:text-gray-200"
                    >
                      <Copy className="w-3.5 h-3.5" />
                      <span>{copiedMessageId === msg.id ? 'Copied' : 'Copy'}</span>
                    </button>
                  </div>
                  <div className={`rounded-lg px-3 py-2 text-sm whitespace-pre-wrap break-words ${
                    msg.role === 'user'
                      ? 'bg-emerald-900/50 text-emerald-100'
                      : 'bg-gray-800 text-gray-200'
                  }`}>
                    {msg.content}
                  </div>
                </div>
              </div>
            ))}

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
                placeholder={selectedAgent ? `Ask ${selectedAgent}…` : 'Select an agent first'}
                disabled={!selectedAgent}
                rows={3}
                className="flex-1 resize-none bg-gray-800 text-gray-200 text-sm rounded px-3 py-2 border border-gray-600 focus:outline-none focus:border-emerald-500 placeholder-gray-600"
              />
              <button
                onClick={send}
                disabled={!selectedAgent || !input.trim() || sending}
                className="flex-shrink-0 flex items-center gap-1.5 px-4 py-2 bg-emerald-700 hover:bg-emerald-600 disabled:bg-gray-700 disabled:text-gray-500 text-white text-sm rounded transition-colors"
              >
                <Send className="w-4 h-4" />
                Send
              </button>
            </div>
            <p className="text-xs text-gray-600 mt-1">Enter to send, Shift+Enter for newline</p>
          </div>
        </section>

        {/* Right column: agent-dependent extra info */}
        <aside className="flex flex-col min-h-0 bg-gray-950">
          <div className="px-4 py-2 border-b border-gray-700 bg-gray-900">
            <h3 className="text-sm text-gray-200 font-medium">Agent Context</h3>
          </div>
          <div className="flex-1 min-h-0 p-4 overflow-auto">
            {!selectedAgent && (
              <p className="text-sm text-gray-500">Select an agent to see additional context.</p>
            )}
            {selectedAgent && !selectedAgent.includes('-AA-') && (
              <p className="text-sm text-gray-500">
                No additional visualization for this agent type yet.
              </p>
            )}
            {selectedAgent && selectedAgent.includes('-AA-') && (
              <div className="h-full min-h-[280px] flex flex-col gap-3">
                <div className="flex items-center gap-3">
                  <p className="text-xs text-gray-400">
                    Last 100 {chartTimeframe} candles for {selectedAgent}
                  </p>
                  <span
                    className={[
                      'text-xs min-w-[130px] text-right',
                      candlesLoading ? 'text-gray-500 animate-pulse' : 'text-transparent',
                    ].join(' ')}
                    aria-live="polite"
                  >
                    Refreshing candles...
                  </span>
                </div>
                {candlesError && <p className="text-sm text-red-400">Error: {candlesError}</p>}
                <>
                  <div className="h-1/2 min-h-[260px]">
                    {candles.length > 0 ? (
                      <ForexChart
                        candles={candles}
                        markers={analysisMarkers}
                        controls={(
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
                          </>
                        )}
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
                  <div className="flex-1 min-h-0 border border-gray-800 rounded p-3 text-xs text-gray-500 bg-gray-900/40">
                    Analysis markers come from persisted `analysis_result` events and do not change the live AA workflow.
                  </div>
                </>
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
              <pre className="whitespace-pre-wrap break-words text-sm text-gray-200 leading-6">
                {selectedAnalysis.analysis_text || JSON.stringify(selectedAnalysis.analysis ?? selectedAnalysis.output, null, 2)}
              </pre>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}








