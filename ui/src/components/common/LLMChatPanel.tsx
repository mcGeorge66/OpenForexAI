import React, { useEffect, useRef, useState } from 'react'
import { Bot, ChevronDown, ChevronUp, CornerDownLeft, Loader2 } from 'lucide-react'
import { api, type LLMAssistantMessage } from '@/api/client'

interface LLMChatPanelProps {
  /** Current script code — sent as context with every question */
  code: string
  /** Filename inside config/llm_contexts/ (e.g. "script_snapshot_calculation_context.md") */
  contextFile: string
  /** Height of the open panel body in px (controlled externally for resize support). Pass 0 to fill available height via CSS. */
  height?: number
  /** Start the panel in open state (default false) */
  initialOpen?: boolean
}

// ─── Markdown renderer (code blocks only) ────────────────────────────────────

function renderAssistantContent(text: string): React.ReactNode {
  // Split on fenced code blocks: ```lang\n...\n```
  const parts = text.split(/(```[\w]*\n[\s\S]*?```)/g)
  return parts.map((part, i) => {
    const match = part.match(/^```([\w]*)\n([\s\S]*?)```$/)
    if (match) {
      const code = match[2]
      return (
        <pre
          key={i}
          className="my-1.5 rounded bg-gray-900 border border-gray-700 px-3 py-2 text-[11px] font-mono text-emerald-300 overflow-x-auto whitespace-pre"
        >
          {code}
        </pre>
      )
    }
    // Inline code: `...`
    const inlineParts = part.split(/(`[^`]+`)/g)
    if (inlineParts.length === 1) return <span key={i}>{part}</span>
    return (
      <span key={i}>
        {inlineParts.map((s, j) => {
          const m = s.match(/^`([^`]+)`$/)
          if (m) return <code key={j} className="rounded bg-gray-900 border border-gray-700 px-1 font-mono text-emerald-300 text-[11px]">{m[1]}</code>
          return <span key={j}>{s}</span>
        })}
      </span>
    )
  })
}

export function LLMChatPanel({ code, contextFile, height = 280, initialOpen = false }: LLMChatPanelProps) {
  const [open, setOpen]       = useState(initialOpen)
  const [input, setInput]     = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError]     = useState<string | null>(null)
  const [history, setHistory] = useState<LLMAssistantMessage[]>([])

  const bottomRef   = useRef<HTMLDivElement | null>(null)
  const inputRef    = useRef<HTMLTextAreaElement | null>(null)
  const historyRef  = useRef<LLMAssistantMessage[]>([])
  historyRef.current = history

  // Scroll to bottom whenever a new message arrives
  useEffect(() => {
    if (open) bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [history, open])

  // Focus input when panel opens
  useEffect(() => {
    if (open) setTimeout(() => inputRef.current?.focus(), 50)
  }, [open])

  const send = async () => {
    const question = input.trim()
    if (!question || loading) return

    const userMsg: LLMAssistantMessage = { role: 'user', content: question }
    setHistory(h => [...h, userMsg])
    setInput('')
    setLoading(true)
    setError(null)

    try {
      const resp = await api.llmAssistantChat({
        context_file: contextFile,
        script: code,
        question,
        history: historyRef.current,
      })
      if (resp.error) {
        setError(resp.error)
      } else {
        setHistory(h => [...h, { role: 'assistant', content: resp.answer }])
      }
    } catch (e: unknown) {
      setError(String(e))
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
    <div className="flex-shrink-0 border-t border-gray-700 bg-gray-950">
      {/* Toggle header */}
      <button
        type="button"
        onClick={() => setOpen(v => !v)}
        className="w-full flex items-center gap-2 px-4 py-2 text-xs text-gray-400 hover:text-gray-200 hover:bg-gray-900/60 transition-colors select-none"
      >
        <Bot className="w-3.5 h-3.5 flex-shrink-0" />
        <span className="flex-1 text-left font-medium">Script Assistant</span>
        {open
          ? <ChevronDown className="w-3.5 h-3.5 flex-shrink-0" />
          : <ChevronUp   className="w-3.5 h-3.5 flex-shrink-0" />
        }
      </button>

      {open && (
        <div className="flex flex-col" style={{ height: height ? `${height}px` : '100%' }}>
          {/* Messages */}
          <div className="flex-1 overflow-y-auto px-4 py-2 space-y-3 min-h-0">
            {history.length === 0 && !loading && (
              <p className="text-xs text-gray-600 italic">
                Ask a question about the script — what variables are available, how to access indicator data, etc.
              </p>
            )}
            {history.map((msg, i) => (
              <div key={i} className={msg.role === 'user' ? 'flex justify-end' : 'flex justify-start'}>
                <div
                  className={
                    msg.role === 'user'
                      ? 'max-w-[80%] rounded-lg px-3 py-1.5 text-xs bg-blue-900/60 text-blue-100'
                      : 'max-w-[90%] rounded-lg px-3 py-1.5 text-xs bg-gray-800 text-gray-200 whitespace-pre-wrap'
                  }
                >
                  {msg.role === 'assistant' ? renderAssistantContent(msg.content) : msg.content}
                </div>
              </div>
            ))}
            {loading && (
              <div className="flex justify-start">
                <div className="flex items-center gap-2 rounded-lg px-3 py-1.5 text-xs bg-gray-800 text-gray-400">
                  <Loader2 className="w-3 h-3 animate-spin" />
                  Thinking…
                </div>
              </div>
            )}
            {error && (
              <p className="text-xs text-red-400">{error}</p>
            )}
            <div ref={bottomRef} />
          </div>

          {/* Input row */}
          <div className="flex-shrink-0 flex items-end gap-2 px-3 py-2 border-t border-gray-800">
            <textarea
              ref={inputRef}
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              rows={2}
              placeholder="Ask about this script… (Enter to send, Shift+Enter for newline)"
              className="flex-1 resize-none bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-xs text-gray-200 placeholder-gray-600 focus:outline-none focus:border-gray-500"
              disabled={loading}
            />
            <button
              type="button"
              onClick={() => void send()}
              disabled={loading || !input.trim()}
              title="Send (Enter)"
              className="flex-shrink-0 flex items-center justify-center w-7 h-7 rounded bg-blue-700 hover:bg-blue-600 text-white disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              <CornerDownLeft className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
