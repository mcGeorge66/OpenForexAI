/**
 * Chart Analysis's assistant panel — always available (not gated on an order being
 * focused), explains whatever's currently on screen and, in order-focus mode, the
 * specific order too. Pure view over useChartAssistantChat; message/tool-event
 * rendering mirrors PromptWorkbench's chat bubble style since both talk to the same
 * /prompt-workbench/chat endpoint and get the same response shape.
 */
import { useEffect, useRef, useState } from 'react'
import { Check, ChevronDown, ChevronUp, Copy, Trash2 } from 'lucide-react'
import type { AnnotationOverlay } from './useAnnotationOverlay'
import { useChartAssistantChat, summarizeToolEvents, type ChartAssistantContext, type ChartAssistantMessage } from './useChartAssistantChat'

export interface ChartAssistantPanelProps {
  overlay: AnnotationOverlay
  context: ChartAssistantContext
}

// "Capped Scroll Box" pattern (docs/ui-patterns.md) — same treatment as Orderbook's
// "Ask AI" window (OrderInvestigateModal.tsx's AssistantMessageBubble): long answers
// default to a capped, scrollable height instead of pushing the whole panel around,
// with "Show more"/"Show less" to remove/reapply the cap and a Copy button. The full
// text is always in the DOM, never truncated — the cap is purely a max-height style.
const COLLAPSED_MAX_LINES = 15
const CAPPED_BOX_MAX_HEIGHT = '16rem'

function ChartAssistantMessageBubble({ msg, toolLines }: { msg: ChartAssistantMessage; toolLines: string[] }) {
  const [expanded, setExpanded] = useState(false)
  const [copied, setCopied] = useState(false)
  const isError = msg.role === 'assistant' && msg.isError

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
      <div className={
        isError
          ? 'rounded-lg px-3 py-1.5 text-xs whitespace-pre-wrap bg-red-950/60 border border-red-800/60 text-red-200'
          : 'rounded-lg px-3 py-1.5 text-xs whitespace-pre-wrap bg-gray-800 text-gray-200'
      }>
        <div
          className={!expanded && isLong ? 'overflow-y-auto pr-1' : undefined}
          style={!expanded && isLong ? { maxHeight: CAPPED_BOX_MAX_HEIGHT } : undefined}
        >
          {msg.content}
        </div>
        {toolLines.length > 0 && (
          <div
            className="mt-1.5 pt-1.5 border-t border-gray-700 text-[10px] text-white font-mono"
            title="Tatsächlich ausgeführte Tool-Aufrufe dieser Antwort — nicht vom Antworttext abgeleitet"
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

export function ChartAssistantPanel({ overlay, context }: ChartAssistantPanelProps) {
  const { messages, input, setInput, sending, send, clearMessages, systemPromptReady, systemPromptError } = useChartAssistantChat(overlay)
  const messagesContainerRef = useRef<HTMLDivElement | null>(null)
  const inputRef = useRef<HTMLTextAreaElement | null>(null)

  useEffect(() => {
    const el = messagesContainerRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [messages.length])

  // Panel mounts fresh each time it's opened (parent renders it conditionally) — focus
  // the input so opening it and typing a question is a single motion, not open-then-click.
  useEffect(() => {
    if (context.pair) inputRef.current?.focus()
  }, [context.pair])

  return (
    <div className="flex flex-col h-full bg-gray-950">
      <div className="flex items-center justify-between px-3 py-1.5 bg-gray-900 border-b border-gray-800 flex-shrink-0">
        <span className="text-xs font-medium text-gray-300">Chart Assistant</span>
        <button
          onClick={clearMessages}
          disabled={messages.length === 0}
          title="Chatverlauf löschen"
          className="flex items-center gap-1 px-2 py-1 rounded border border-gray-700 bg-gray-900 text-gray-300 hover:text-white text-xs disabled:opacity-40"
        >
          <Trash2 className="w-3 h-3" /> Delete
        </button>
      </div>
      {systemPromptError && (
        <div className="px-3 py-1.5 bg-amber-950/60 border-b border-amber-800 text-[11px] text-amber-300 flex-shrink-0">
          Assistent-Konfiguration konnte nicht geladen werden ({systemPromptError}). Antworten können dadurch schlechter ausfallen.
        </div>
      )}
      <div ref={messagesContainerRef} className="flex-1 overflow-y-auto px-3 py-3 space-y-2 min-h-0">
        {messages.length === 0 && (
          <p className="text-xs text-white italic">
            Frag nach dem sichtbaren Chart (Preisverlauf, Indikatoren, Support/Resistance){context.extraSystemPrompt ? ' oder der fokussierten Order (Einstieg, SL/TP, Original-Analyse)' : ''}.
            Der Assistent kann bei Bedarf selbst Marker/Zonen im Chart setzen{context.extraAllowedTools?.length ? ' und zusätzliche Order-Detaildaten nachschlagen (Trace, Kerzen, Agent-Entscheidungen)' : ''}.
          </p>
        )}
        {messages.map(msg => {
          if (msg.role === 'user') {
            return (
              <div key={msg.id} className="flex justify-end">
                <div className="max-w-[90%] rounded-lg px-3 py-1.5 text-xs bg-emerald-900/50 text-emerald-100 whitespace-pre-wrap">
                  {msg.content}
                </div>
              </div>
            )
          }
          const toolLines = summarizeToolEvents(msg.toolEvents)
          return (
            <div key={msg.id} className="flex justify-start">
              <ChartAssistantMessageBubble msg={msg} toolLines={toolLines} />
            </div>
          )
        })}
        {sending && (
          <div className="flex justify-start">
            <div className="bg-gray-800 rounded-lg px-3 py-1.5 text-xs text-gray-400 animate-pulse">
              Waiting for the assistant…
            </div>
          </div>
        )}
      </div>
      <div className="flex-shrink-0 px-3 py-2 border-t border-gray-700 flex gap-2 items-end">
        <textarea
          ref={inputRef}
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault()
              void send(context)
            }
          }}
          rows={2}
          placeholder={context.pair ? 'Frag den Assistenten zum Chart…' : 'Erst ein Pair laden…'}
          disabled={!context.pair}
          className="flex-1 resize-none bg-gray-800 text-gray-200 text-xs rounded px-2 py-1.5 border border-gray-600 focus:outline-none focus:border-emerald-500 placeholder-gray-600 disabled:opacity-50"
        />
        <button
          onClick={() => void send(context)}
          disabled={!input.trim() || sending || !systemPromptReady || !context.pair}
          className="px-3 py-1.5 bg-emerald-700 hover:bg-emerald-600 disabled:bg-gray-700 disabled:text-gray-500 text-white text-xs rounded transition-colors"
        >
          Send
        </button>
      </div>
    </div>
  )
}
