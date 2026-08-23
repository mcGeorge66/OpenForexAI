/**
 * OrderInvestigateModal — "Ask AI" chat scoped to one Orderbook entry.
 *
 * Backed by POST /orderbook/{id}/investigate: a real tool-calling Agent (same
 * pattern as /prompt-workbench/chat), pre-loaded with the order's full record
 * (AA analysis, P&L, close reasoning) and given read-only tools to dig further
 * — the causal event chain, the live agent/EC config that produced/closed it,
 * EC run history, and general market data. Not a static-context assistant like
 * AiAssistantModal: it can actually go fetch more data mid-conversation.
 *
 * A free-floating window (drag by header, resize from the bottom-right corner)
 * rather than a fixed centered modal, so it doesn't block the Orderbook behind it.
 */

import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { Bot, Check, ChevronDown, ChevronUp, Copy, CornerDownLeft, Loader2, PictureInPicture2, X } from 'lucide-react'
import { api, type LLMAssistantMessage, type OrderbookEntryDetail, type PromptWorkbenchToolEvent } from '@/api/client'
import { useDocumentPictureInPicture } from '@/hooks/useDocumentPictureInPicture'

interface ChatMessage extends LLMAssistantMessage {
  id: string
  toolEvents?: PromptWorkbenchToolEvent[]
  error?: string
}

const DEFAULT_WIDTH = 900
const DEFAULT_HEIGHT = 680
const MIN_WIDTH = 420
const MIN_HEIGHT = 320
const COLLAPSED_MAX_LINES = 15

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

// "Capped Scroll Box" pattern — see docs/ui-patterns.md. Collapsed state keeps the
// full text in the DOM (never truncated) inside a fixed max-height, scrollable
// container, so a scrollbar is always an alternative to clicking "Show more".
// "Show more" removes the height cap entirely for a fully unbounded view.
const CAPPED_BOX_MAX_HEIGHT = '16rem'

function AssistantMessageBubble({ msg, toolLines }: { msg: ChatMessage; toolLines: string[] }) {
  const [expanded, setExpanded] = useState(false)
  const [copied, setCopied] = useState(false)

  const lines = msg.content.split('\n')
  const isLong = lines.length > COLLAPSED_MAX_LINES

  const copy = () => {
    void navigator.clipboard.writeText(msg.content).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    })
  }

  return (
    <div className="flex flex-col items-start max-w-[90%] gap-1">
      <div
        className={`rounded-lg px-3 py-1.5 text-xs whitespace-pre-wrap ${
          msg.error ? 'bg-red-900/30 text-red-300' : 'bg-gray-800 text-gray-200'
        }`}
      >
        <div
          className={!expanded && isLong ? 'overflow-y-auto pr-1' : undefined}
          style={!expanded && isLong ? { maxHeight: CAPPED_BOX_MAX_HEIGHT } : undefined}
        >
          {msg.content}
        </div>
        {toolLines.length > 0 && (
          <div
            className="mt-1.5 pt-1.5 border-t border-gray-700 text-[10px] text-white font-mono"
            title="Tool calls actually executed for this response"
          >
            Tools: {toolLines.join(', ')}
          </div>
        )}
      </div>
      <div className="flex items-center gap-3 px-1">
        <button
          type="button"
          onClick={copy}
          className="flex items-center gap-1 text-[10px] text-gray-500 hover:text-gray-300 transition-colors"
        >
          {copied
            ? <><Check className="w-3 h-3 text-emerald-400" /><span className="text-emerald-400">Copied</span></>
            : <><Copy className="w-3 h-3" />Copy</>}
        </button>
        {isLong && (
          <button
            type="button"
            onClick={() => setExpanded(v => !v)}
            className="flex items-center gap-1 text-[10px] text-gray-500 hover:text-gray-300 transition-colors"
          >
            {expanded
              ? <><ChevronUp className="w-3 h-3" />Show less</>
              : <><ChevronDown className="w-3 h-3" />Show more ({lines.length} lines)</>}
          </button>
        )}
      </div>
    </div>
  )
}

export function OrderInvestigateModal({ orderId, onClose }: { orderId: string; onClose: () => void }) {
  const [entry, setEntry] = useState<OrderbookEntryDetail | null>(null)
  const [entryError, setEntryError] = useState<string | null>(null)
  const [history, setHistory] = useState<ChatMessage[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)

  const [size, setSize] = useState(() => ({
    width: Math.max(MIN_WIDTH, Math.min(DEFAULT_WIDTH, window.innerWidth - 32)),
    height: Math.max(MIN_HEIGHT, Math.min(DEFAULT_HEIGHT, window.innerHeight - 32)),
  }))
  const [pos, setPos] = useState(() => ({
    x: Math.max(16, (window.innerWidth - Math.min(DEFAULT_WIDTH, window.innerWidth - 32)) / 2),
    y: Math.max(16, (window.innerHeight - Math.min(DEFAULT_HEIGHT, window.innerHeight - 32)) / 2),
  }))
  const dragState = useRef<{ startX: number; startY: number; origX: number; origY: number } | null>(null)
  const resizeState = useRef<{ startX: number; startY: number; origW: number; origH: number } | null>(null)

  const { pipWindow, open: popOut, close: redock, supported: pipSupported } =
    useDocumentPictureInPicture({ width: size.width, height: size.height })

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

  // Window drag (from header) + resize (from bottom-right handle), same
  // global-listener pattern used by the AgentChat split-pane divider.
  useEffect(() => {
    const onMouseMove = (e: MouseEvent) => {
      if (dragState.current) {
        const { startX, startY, origX, origY } = dragState.current
        setPos({
          x: Math.min(Math.max(0, origX + (e.clientX - startX)), window.innerWidth - 120),
          y: Math.min(Math.max(0, origY + (e.clientY - startY)), window.innerHeight - 48),
        })
      }
      if (resizeState.current) {
        const { startX, startY, origW, origH } = resizeState.current
        setSize({
          width: Math.max(MIN_WIDTH, origW + (e.clientX - startX)),
          height: Math.max(MIN_HEIGHT, origH + (e.clientY - startY)),
        })
      }
    }
    const onMouseUp = () => { dragState.current = null; resizeState.current = null }
    window.addEventListener('mousemove', onMouseMove)
    window.addEventListener('mouseup', onMouseUp)
    return () => {
      window.removeEventListener('mousemove', onMouseMove)
      window.removeEventListener('mouseup', onMouseUp)
    }
  }, [])

  const startDrag = (e: React.MouseEvent) => {
    dragState.current = { startX: e.clientX, startY: e.clientY, origX: pos.x, origY: pos.y }
  }
  const startResize = (e: React.MouseEvent) => {
    e.stopPropagation()
    resizeState.current = { startX: e.clientX, startY: e.clientY, origW: size.width, origH: size.height }
  }

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

  const header = (
    <div
      className={`flex items-center justify-between px-4 py-2 bg-gray-900 border-b border-gray-700 flex-shrink-0 select-none ${pipWindow ? '' : 'cursor-move'}`}
      onMouseDown={pipWindow ? undefined : startDrag}
    >
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
      <div className="flex items-center gap-3 flex-shrink-0">
        {pipWindow ? (
          <button
            onClick={redock}
            onMouseDown={e => e.stopPropagation()}
            title="Zurück ins Browserfenster andocken"
            className="text-gray-500 hover:text-gray-300"
          >
            <PictureInPicture2 className="w-4 h-4" />
          </button>
        ) : (
          <>
            {pipSupported && (
              <button
                onClick={() => void popOut()}
                onMouseDown={e => e.stopPropagation()}
                title="Als eigenes Fenster lösen (aus dem Browser herausziehbar)"
                className="text-gray-500 hover:text-gray-300"
              >
                <PictureInPicture2 className="w-4 h-4" />
              </button>
            )}
            <button
              onClick={onClose}
              onMouseDown={e => e.stopPropagation()}
              className="text-gray-500 hover:text-gray-300"
            >
              <X className="w-4 h-4" />
            </button>
          </>
        )}
      </div>
    </div>
  )

  const body = (
    <>
      {entryError && (
        <div className="px-4 py-2 text-xs text-red-400 bg-red-900/20 flex-shrink-0">{entryError}</div>
      )}

      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-3 min-h-0">
        {history.length === 0 && (
          <p className="text-xs text-white italic">
            Ask anything about this trade — e.g. "why was this order closed here?" or "if I want
            to adjust the entry filter, where do I do that?". The model already knows the full
            analysis for this order and can look up more on its own if needed (event trace,
            agent/EC config, market data).
          </p>
        )}
        {history.map(msg => {
          if (msg.role === 'user') {
            return (
              <div key={msg.id} className="flex justify-end">
                <div className="max-w-[85%] rounded-lg px-3 py-1.5 text-xs bg-emerald-900/50 text-emerald-100 whitespace-pre-wrap">
                  {msg.content}
                </div>
              </div>
            )
          }
          const toolLines = summarizeToolEvents(msg.toolEvents)
          return (
            <div key={msg.id} className="flex justify-start">
              <AssistantMessageBubble msg={msg} toolLines={toolLines} />
            </div>
          )
        })}
        {loading && (
          <div className="flex justify-start">
            <div className="flex items-center gap-2 rounded-lg px-3 py-1.5 text-xs bg-gray-800 text-white">
              <Loader2 className="w-3 h-3 animate-spin" />
              Investigating the trade…
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
          placeholder="Ask about this trade… (Enter to send, Shift+Enter for newline)"
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
    </>
  )

  if (pipWindow) {
    return createPortal(
      <div className="flex flex-col h-screen bg-gray-950">
        {header}
        {body}
      </div>,
      pipWindow.document.body,
    )
  }

  return (
    <div
      className="fixed z-50 flex flex-col bg-gray-950 rounded-lg overflow-hidden shadow-2xl border border-gray-700"
      style={{ left: pos.x, top: pos.y, width: size.width, height: size.height }}
    >
      {header}
      {body}
      <div
        onMouseDown={startResize}
        title="Resize"
        className="absolute bottom-0 right-0 w-4 h-4 cursor-nwse-resize"
      >
        <div className="absolute bottom-0.5 right-0.5 w-2.5 h-2.5 border-b-2 border-r-2 border-gray-600 rounded-br-sm" />
      </div>
    </div>
  )
}
