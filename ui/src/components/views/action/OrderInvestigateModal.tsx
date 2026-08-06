/**
 * OrderInvestigateModal — "Ask AI" chat scoped to one Orderbook entry.
 *
 * Backed by POST /orderbook/{id}/investigate: a real tool-calling Agent (same
 * pattern as /prompt-workbench/chat), pre-loaded with the order's full record
 * (AA analysis, P&L, close reasoning) and given read-only tools to dig further
 * — the causal event chain, the live agent/EC config that produced/closed it,
 * EC run history, and general market data. Not a static-context assistant like
 * AiAssistantModal: it can actually go fetch more data mid-conversation.
 */

import { useEffect, useRef, useState } from 'react'
import { Bot, CornerDownLeft, Loader2, X } from 'lucide-react'
import { api, type LLMAssistantMessage, type OrderbookEntryDetail, type PromptWorkbenchToolEvent } from '@/api/client'

interface ChatMessage extends LLMAssistantMessage {
  id: string
  toolEvents?: PromptWorkbenchToolEvent[]
  error?: string
}

// One line per tool call, e.g. "get_order_trace OK" / "get_agent_config FAILED" —
// same pairing logic PromptWorkbench.tsx uses for its own tool-event summaries.
function summarizeToolEvents(events: PromptWorkbenchToolEvent[] | undefined): string[] {
  if (!events?.length) return []
  const lines: string[] = []
  let pendingName: string | null = null
  for (const evt of events) {
    if (evt.event_type === 'tool_call_started') {
      pendingName = evt.payload.tool_name ?? '?'
      continue
    }
    const name = evt.payload.tool_name ?? pendingName ?? '?'
    let status = 'OK'
    if (evt.event_type === 'tool_call_failed') {
      status = 'FAILED'
    } else {
      try {
        const parsed = JSON.parse(evt.payload.result ?? '{}')
        if (parsed && typeof parsed === 'object' && 'error' in parsed) status = 'REJECTED'
      } catch { /* non-JSON result — treat as OK */ }
    }
    lines.push(`${name} ${status}`)
    pendingName = null
  }
  return lines
}

function formatMoney(v: number | null | undefined): string {
  if (v === null || v === undefined) return '–'
  return `${v >= 0 ? '+' : ''}${v.toFixed(2)}`
}

export function OrderInvestigateModal({ orderId, onClose }: { orderId: string; onClose: () => void }) {
  const [entry, setEntry] = useState<OrderbookEntryDetail | null>(null)
  const [entryError, setEntryError] = useState<string | null>(null)
  const [history, setHistory] = useState<ChatMessage[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)

  const bottomRef = useRef<HTMLDivElement | null>(null)
  const inputRef = useRef<HTMLTextAreaElement | null>(null)
  const historyRef = useRef(history)
  historyRef.current = history

  useEffect(() => {
    api.getOrderbookEntry(orderId).then(setEntry).catch(e => setEntryError(String(e)))
  }, [orderId])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [history])

  useEffect(() => {
    setTimeout(() => inputRef.current?.focus(), 50)
  }, [])

  const send = async () => {
    const question = input.trim()
    if (!question || loading) return

    const userMsg: ChatMessage = { id: `u_${Date.now()}`, role: 'user', content: question }
    setHistory(h => [...h, userMsg])
    setInput('')
    setLoading(true)

    try {
      const resp = await api.investigateOrder(orderId, {
        question,
        history: historyRef.current.map(m => ({ role: m.role, content: m.content })),
      })
      setHistory(h => [...h, {
        id: `a_${Date.now()}`,
        role: 'assistant',
        content: resp.error ? `Error: ${resp.error}` : (resp.answer || '(empty response)'),
        toolEvents: resp.tool_events,
        error: resp.error ?? undefined,
      }])
    } catch (e) {
      setHistory(h => [...h, { id: `a_${Date.now()}`, role: 'assistant', content: `Error: ${String(e)}`, error: String(e) }])
    } finally {
      setLoading(false)
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      void send()
    }
  }

  return (
    <div className="flex flex-col h-full bg-gray-950 rounded-lg overflow-hidden">
      <div className="flex items-center justify-between px-4 py-2 bg-gray-900 border-b border-gray-700 flex-shrink-0">
        <div className="flex items-center gap-2 min-w-0">
          <Bot className="w-4 h-4 text-emerald-400 flex-shrink-0" />
          <span className="text-xs font-semibold text-emerald-400 uppercase tracking-wider flex-shrink-0">
            Ask AI — Order
          </span>
          {entry && (
            <span className="text-xs text-gray-400 truncate">
              {entry.pair} {entry.direction} · {entry.status} · {formatMoney(entry.pnl_account_currency)}
            </span>
          )}
        </div>
        <button onClick={onClose} className="text-gray-500 hover:text-gray-300 flex-shrink-0">
          <X className="w-4 h-4" />
        </button>
      </div>

      {entryError && (
        <div className="px-4 py-2 text-xs text-red-400 bg-red-900/20 flex-shrink-0">{entryError}</div>
      )}

      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-3 min-h-0">
        {history.length === 0 && (
          <p className="text-xs text-white italic">
            Frag alles zu diesem Trade — z.B. "warum wurde die Order hier beendet?" oder
            "wenn ich den Einstiegsfilter anpassen will, wo mache ich das?". Das Modell kennt
            bereits die vollständige Analyse dieses Orders und kann bei Bedarf selbst weiter
            nachschauen (Event-Trace, Agent-/EC-Konfiguration, Kursdaten).
          </p>
        )}
        {history.map(msg => {
          const toolLines = msg.role === 'assistant' ? summarizeToolEvents(msg.toolEvents) : []
          return (
            <div key={msg.id} className={msg.role === 'user' ? 'flex justify-end' : 'flex justify-start'}>
              <div
                className={
                  msg.role === 'user'
                    ? 'max-w-[85%] rounded-lg px-3 py-1.5 text-xs bg-emerald-900/50 text-emerald-100 whitespace-pre-wrap'
                    : `max-w-[90%] rounded-lg px-3 py-1.5 text-xs whitespace-pre-wrap ${
                        msg.error ? 'bg-red-900/30 text-red-300' : 'bg-gray-800 text-gray-200'
                      }`
                }
              >
                {msg.content}
                {toolLines.length > 0 && (
                  <div
                    className="mt-1.5 pt-1.5 border-t border-gray-700 text-[10px] text-white font-mono"
                    title="Tatsächlich ausgeführte Tool-Aufrufe dieser Antwort"
                  >
                    Tools: {toolLines.join(', ')}
                  </div>
                )}
              </div>
            </div>
          )
        })}
        {loading && (
          <div className="flex justify-start">
            <div className="flex items-center gap-2 rounded-lg px-3 py-1.5 text-xs bg-gray-800 text-white">
              <Loader2 className="w-3 h-3 animate-spin" />
              Untersucht den Trade…
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      <div className="flex-shrink-0 flex items-end gap-2 px-3 py-2 border-t border-gray-800">
        <textarea
          ref={inputRef}
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          rows={2}
          placeholder="Frage zu diesem Trade… (Enter zum Senden, Shift+Enter für neue Zeile)"
          className="flex-1 resize-none bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-xs text-gray-200 placeholder-gray-600 focus:outline-none focus:border-gray-500"
          disabled={loading}
        />
        <button
          type="button"
          onClick={() => void send()}
          disabled={loading || !input.trim()}
          title="Send (Enter)"
          className="flex-shrink-0 flex items-center justify-center w-7 h-7 rounded bg-emerald-700 hover:bg-emerald-600 text-white disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
        >
          <CornerDownLeft className="w-3.5 h-3.5" />
        </button>
      </div>
    </div>
  )
}
