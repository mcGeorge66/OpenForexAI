import React, { useEffect, useRef, useState } from 'react'
import { Bot, Check, Copy, CornerDownLeft, Loader2, X } from 'lucide-react'
import { api, type LLMAssistantMessage } from '@/api/client'

// ── Persistent history store (survives modal close, cleared on page reload) ───
const _historyStore = new Map<string, LLMAssistantMessage[]>()

// ── Markdown renderer (code blocks + inline code) ────────────────────────────
function renderContent(text: string): React.ReactNode {
  const parts = text.split(/(```[\w]*\n[\s\S]*?```)/g)
  return parts.map((part, i) => {
    const fence = part.match(/^```([\w]*)\n([\s\S]*?)```$/)
    if (fence) {
      return (
        <pre key={i} className="my-1.5 rounded bg-gray-900 border border-gray-700 px-3 py-2 text-[11px] font-mono text-emerald-300 overflow-x-auto whitespace-pre">
          {fence[2]}
        </pre>
      )
    }
    const inline = part.split(/(`[^`]+`)/g)
    if (inline.length === 1) return <span key={i}>{part}</span>
    return (
      <span key={i}>
        {inline.map((s, j) => {
          const m = s.match(/^`([^`]+)`$/)
          if (m) return <code key={j} className="rounded bg-gray-900 border border-gray-700 px-1 font-mono text-emerald-300 text-[11px]">{m[1]}</code>
          return <span key={j}>{s}</span>
        })}
      </span>
    )
  })
}

export interface AiAssistantModalProps {
  /** Window title shown in the modal header */
  title: string
  /** Filename inside config/llm_contexts/ (e.g. "snapshot_config_assistant.md") */
  contextFile: string
  /** Current context data to pass alongside each message (e.g. serialized JSON of current config) */
  contextData?: string
  /** Human-readable label for the context data shown in the modal */
  contextDataLabel?: string
  onClose: () => void
}

export function AiAssistantModal({
  title,
  contextFile,
  contextData,
  contextDataLabel,
  onClose,
}: AiAssistantModalProps) {
  const [history, setHistory] = useState<LLMAssistantMessage[]>(
    () => _historyStore.get(contextFile) ?? []
  )
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [copiedIdx, setCopiedIdx] = useState<number | null>(null)

  const bottomRef = useRef<HTMLDivElement | null>(null)
  const inputRef = useRef<HTMLTextAreaElement | null>(null)
  const historyRef = useRef<LLMAssistantMessage[]>(history)
  historyRef.current = history

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [history])

  useEffect(() => {
    setTimeout(() => inputRef.current?.focus(), 50)
  }, [])

  // Sync history to module-level store so it survives modal close/reopen
  useEffect(() => {
    _historyStore.set(contextFile, history)
  }, [contextFile, history])

  // Close on Escape
  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onClose])

  const send = async () => {
    const question = input.trim()
    if (!question || loading) return

    const userMsg: LLMAssistantMessage = { role: 'user', content: question }
    const nextHistory = [...historyRef.current, userMsg]
    setHistory(nextHistory)
    setInput('')
    setLoading(true)
    setError(null)

    try {
      const resp = await api.llmAssistantChat({
        context_file: contextFile,
        question,
        history: historyRef.current,
        context_data: contextData,
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

  const clearChat = () => {
    setHistory([])
    _historyStore.delete(contextFile)
    setError(null)
  }

  const copyMessage = (content: string, idx: number) => {
    void navigator.clipboard.writeText(content).then(() => {
      setCopiedIdx(idx)
      setTimeout(() => setCopiedIdx(null), 1800)
    })
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      void send()
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
      onClick={e => { if (e.target === e.currentTarget) onClose() }}
    >
      <div className="flex flex-col w-full max-w-2xl h-[80vh] bg-gray-900 border border-gray-700 rounded-lg shadow-2xl">

        {/* Header */}
        <div className="flex items-center gap-2 px-4 py-2.5 border-b border-gray-700 bg-gray-800 rounded-t-lg flex-shrink-0">
          <Bot className="w-4 h-4 text-blue-400 flex-shrink-0" />
          <span className="text-sm font-medium text-gray-200 flex-1">{title}</span>
          {contextDataLabel && (
            <span className="text-xs text-white truncate max-w-[200px]" title={contextDataLabel}>
              {contextDataLabel}
            </span>
          )}
          <button
            onClick={clearChat}
            disabled={history.length === 0}
            className="text-xs px-2 py-0.5 rounded border border-red-800 bg-red-900/30 text-red-400 hover:bg-red-900/60 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            Clear
          </button>
          <button
            onClick={onClose}
            className="text-gray-500 hover:text-white transition-colors ml-1"
            title="Close (Esc)"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto px-4 py-3 space-y-3 min-h-0">
          {history.length === 0 && !loading && (
            <p className="text-xs text-white italic mt-8 text-center">
              Ask a question about the current configuration…
              <br />
              <span className="text-gray-700">Enter to send · Shift+Enter for newline · Esc to close</span>
            </p>
          )}
          {history.map((msg, i) => (
            <div key={i} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
              <div className="flex flex-col gap-1 max-w-[85%]">
                <div
                  className={
                    msg.role === 'user'
                      ? 'rounded-lg px-3 py-2 text-xs bg-blue-900/60 text-blue-100 whitespace-pre-wrap'
                      : 'rounded-lg px-3 py-2 text-xs bg-gray-800 text-gray-200 whitespace-pre-wrap'
                  }
                >
                  {msg.role === 'assistant' ? renderContent(msg.content) : msg.content}
                </div>
                <button
                  onClick={() => copyMessage(msg.content, i)}
                  className={`flex items-center gap-1 text-[11px] transition-colors ${
                    msg.role === 'user' ? 'self-end' : 'self-start'
                  } text-white hover:text-white`}
                >
                  {copiedIdx === i
                    ? <><Check className="w-3 h-3 text-emerald-400" /><span className="text-emerald-400">Copied</span></>
                    : <><Copy className="w-3 h-3" />Copy</>
                  }
                </button>
              </div>
            </div>
          ))}
          {loading && (
            <div className="flex justify-start">
              <div className="flex items-center gap-2 rounded-lg px-3 py-2 text-xs bg-gray-800 text-white">
                <Loader2 className="w-3 h-3 animate-spin" />
                Thinking…
              </div>
            </div>
          )}
          {error && <p className="text-xs text-red-400 px-1">{error}</p>}
          <div ref={bottomRef} />
        </div>

        {/* Input */}
        <div className="flex-shrink-0 flex items-end gap-2 px-3 py-3 border-t border-gray-700">
          <textarea
            ref={inputRef}
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            rows={2}
            placeholder="Ask a question… (Enter to send, Shift+Enter for newline)"
            className="flex-1 resize-none bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-xs text-gray-200 placeholder-gray-600 focus:outline-none focus:border-blue-500"
            disabled={loading}
          />
          <button
            type="button"
            onClick={() => void send()}
            disabled={loading || !input.trim()}
            title="Send (Enter)"
            className="flex-shrink-0 flex items-center justify-center w-8 h-8 rounded bg-blue-700 hover:bg-blue-600 text-white disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            <CornerDownLeft className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>
    </div>
  )
}
