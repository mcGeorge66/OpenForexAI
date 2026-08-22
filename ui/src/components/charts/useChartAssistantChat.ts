/**
 * Chat assistant for Chart Analysis — explains the currently visible chart, and
 * (when order-focus context is supplied by the caller) the specific order that
 * led there. Calls the exact same POST /prompt-workbench/chat endpoint and base
 * tool set (zone_marker/trade_marker/candle_marker/get_annotation/assessment_memory)
 * the Simulation tab already uses — no second tool-calling implementation. Pair
 * with useAnnotationOverlay for the same chart so tool-drawn markers render
 * identically to the Simulation tab.
 */
import { useCallback, useEffect, useState } from 'react'
import { api, type PromptWorkbenchToolEvent } from '@/api/client'
import type { AnnotationOverlay } from './useAnnotationOverlay'

export interface ChartAssistantMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  timestamp: string
  toolEvents?: PromptWorkbenchToolEvent[]
  /** True for send failures (network/HTTP) and application-level errors, so the panel
   * can render them distinctly from a normal answer instead of looking like a stuck bot. */
  isError?: boolean
}

const BASE_ALLOWED_TOOLS = ['zone_marker', 'trade_marker', 'candle_marker', 'get_annotation', 'assessment_memory']

function now(): string {
  return new Date().toISOString().replace('T', ' ').substring(11, 19) + ' UTC'
}

// api/client.ts's post()/get() throw plain Error(`... → ${status}: ${detail}`) — turn that (and
// bare network failures) into something a user can act on instead of a raw "Error: Error: POST
// /prompt-workbench/chat → 404: " string in a chat bubble. 404 specifically means the backend
// process hasn't picked up this route yet (Python has no hot-reload for route registrations).
function describeSendError(err: unknown): string {
  const raw = err instanceof Error ? err.message : String(err)
  const statusMatch = raw.match(/→\s*(\d{3}):\s*([\s\S]*)$/)
  if (statusMatch) {
    const status = Number(statusMatch[1])
    if (status === 404) {
      return 'Der Assistant-Endpoint ist auf dem Server nicht erreichbar (404) — vermutlich muss der ' +
        'Python-Backend-Prozess neu gestartet werden, um diese Route zu laden.'
    }
    const detail = statusMatch[2].trim()
    return `Der Server hat die Anfrage abgelehnt (HTTP ${status})${detail ? `: ${detail}` : ''}.`
  }
  if (err instanceof TypeError || /failed to fetch|networkerror|load failed/i.test(raw)) {
    return 'Der Server ist gerade nicht erreichbar (Netzwerkfehler) — bitte prüfen, ob das Backend läuft, und es erneut versuchen.'
  }
  return `Unerwarteter Fehler beim Senden: ${raw}`
}

// One line per tool call, e.g. "trade_marker(open) OK" / "assessment_memory FAILED" —
// mirrors PromptWorkbench's summarizeToolEvents (same event shape, same pairing logic).
export function summarizeToolEvents(events: PromptWorkbenchToolEvent[] | undefined): string[] {
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

export interface ChartAssistantContext {
  pair: string
  brokerName: string | null
  timeframe: string
  candleCount: number
  candleAnchor: string | null
  /** Appended to the chart_analysis_assistant.md persona — order-focus mode's order
   * data (analysis_text, fill/close/SL/TP), or omit when nothing is focused. */
  extraSystemPrompt?: string
  /** Additional tool names available only in order-focus mode (the former Investigate
   * modal's read-only tools) — merged with the base marker/memory tool set. */
  extraAllowedTools?: string[]
  llmName?: string | null
  reasoningEffort?: string | null
}

export function useChartAssistantChat(overlay: AnnotationOverlay) {
  const [messages, setMessages] = useState<ChartAssistantMessage[]>([])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [systemPromptBase, setSystemPromptBase] = useState<string | null>(null)
  // Distinct from "loaded but empty" — surfaced in the panel so the user knows the
  // assistant is running without its persona/tool instructions instead of silently
  // getting worse answers.
  const [systemPromptError, setSystemPromptError] = useState<string | null>(null)

  useEffect(() => {
    api.llmContextGet('chart_analysis_assistant.md')
      .then(r => { setSystemPromptBase(r.content); setSystemPromptError(null) })
      .catch(err => { setSystemPromptBase(''); setSystemPromptError(describeSendError(err)) })
  }, [])

  const pushMessage = useCallback((role: ChartAssistantMessage['role'], content: string, toolEvents?: PromptWorkbenchToolEvent[], isError?: boolean) => {
    setMessages(prev => [...prev, {
      id: `${role}-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`, role, content, timestamp: now(), toolEvents, isError,
    }])
  }, [])

  const clearMessages = useCallback(() => setMessages([]), [])

  const send = useCallback(async (ctx: ChartAssistantContext) => {
    const question = input.trim()
    if (!question || sending || systemPromptBase === null || !ctx.pair) return
    const history = messages.map(m => ({ role: m.role, content: m.content }))
    setInput('')
    pushMessage('user', question)
    setSending(true)
    try {
      const systemPrompt = ctx.extraSystemPrompt ? `${systemPromptBase}\n\n${ctx.extraSystemPrompt}` : systemPromptBase
      const resp = await api.promptWorkbenchChat({
        system_prompt: systemPrompt,
        question,
        history,
        pair: ctx.pair,
        broker_name: ctx.brokerName,
        timeframe: ctx.timeframe,
        candle_count: ctx.candleCount,
        candle_anchor: ctx.candleAnchor,
        llm_name: ctx.llmName ?? undefined,
        reasoning_effort: ctx.reasoningEffort ?? undefined,
        allowed_tools: [...BASE_ALLOWED_TOOLS, ...(ctx.extraAllowedTools ?? [])],
        existing_annotations: overlay.annotations,
      })
      pushMessage('assistant', resp.error ? `Fehler: ${resp.error}` : (resp.answer || '(leere Antwort)'), resp.tool_events, !!resp.error)
      overlay.applyAnnotationUpdates(resp)
    } catch (err) {
      pushMessage('assistant', describeSendError(err), undefined, true)
    } finally {
      setSending(false)
    }
  }, [input, sending, messages, systemPromptBase, overlay, pushMessage])

  return {
    messages, input, setInput, sending, send, clearMessages,
    systemPromptReady: systemPromptBase !== null,
    systemPromptError,
  }
}
