/**
 * EntityAssistantPanel — full-height LLM chat view for EventComposer entities.
 * Purely presentational — all state/logic lives in useEntityAssistantChat
 * (own file, a Fast Refresh requirement: this file must only export the
 * component). Create the chat once with the hook and pass it into as many
 * `<EntityAssistantPanel chat={...} />` renderings as needed — e.g. the EC
 * wizard's own "LLM Assistant" tab AND the fullscreen Script editor's
 * "Assistant" tab — and both stay in sync since they share one state object.
 *
 * Supports full script/config replacement, line-number patches, and an
 * agentic debug loop (auto-test + auto-fix up to MAX_AUTO_ITERATIONS) via
 * structured tool-call proposals (see assistantShared.tsx) rather than
 * free-text markup.
 */

import { useEffect, useRef } from 'react'
import type React from 'react'
import { Bot, CornerDownLeft, Loader2, Pencil, FlaskConical, Trash2 } from 'lucide-react'
import { MessageBubble } from '@/components/common/MessageBubble'
import type { EntityAssistantChat } from '@/components/common/useEntityAssistantChat'

export function EntityAssistantPanel({ chat }: { chat: EntityAssistantChat }) {
  const {
    history, input, setInput, loading, error,
    autoWrite, setAutoWrite, canTest, setCanTest,
    send, clearChat, script, configJson, onApplyScript, onApplyConfig,
  } = chat

  const bottomRef = useRef<HTMLDivElement | null>(null)
  const inputRef = useRef<HTMLTextAreaElement | null>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [history])

  useEffect(() => {
    setTimeout(() => inputRef.current?.focus(), 50)
  }, [])

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() }
  }

  return (
    <div className="flex flex-col h-full border border-gray-700 rounded bg-gray-950">
      {/* ── Header ── */}
      <div className="flex items-center gap-2 px-3 py-2 select-none flex-shrink-0 border-b border-gray-700">
        <div className="flex items-center gap-2 flex-1 text-xs text-white">
          <Bot className="w-3.5 h-3.5 flex-shrink-0 text-indigo-400" />
          <span className="font-medium text-left flex-1">Entity Assistant</span>
        </div>

        <div className="flex items-center gap-3 text-[11px]">
          <label className="flex items-center gap-1.5 cursor-pointer select-none"
            title="Code-Blöcke und Patches sofort anwenden">
            <div onClick={() => setAutoWrite(v => !v)}
              className={['relative w-7 h-4 rounded-full transition-colors cursor-pointer', autoWrite ? 'bg-emerald-600' : 'bg-gray-700'].join(' ')}>
              <div className={['absolute top-0.5 w-3 h-3 rounded-full bg-white transition-transform', autoWrite ? 'translate-x-3.5' : 'translate-x-0.5'].join(' ')} />
            </div>
            <Pencil className="w-3 h-3 text-gray-500" />
            <span className={autoWrite ? 'text-emerald-400' : 'text-gray-600'}>Auto-Write</span>
          </label>

          <label className="flex items-center gap-1.5 cursor-pointer select-none"
            title="LLM darf Tests auslösen und selbst debuggen">
            <div onClick={() => setCanTest(v => !v)}
              className={['relative w-7 h-4 rounded-full transition-colors cursor-pointer', canTest ? 'bg-amber-600' : 'bg-gray-700'].join(' ')}>
              <div className={['absolute top-0.5 w-3 h-3 rounded-full bg-white transition-transform', canTest ? 'translate-x-3.5' : 'translate-x-0.5'].join(' ')} />
            </div>
            <FlaskConical className="w-3 h-3 text-gray-500" />
            <span className={canTest ? 'text-amber-400' : 'text-gray-600'}>Kann testen</span>
          </label>

          {history.length > 0 && (
            <button type="button" onClick={clearChat}
              title="Chat leeren" className="text-gray-600 hover:text-red-400 transition-colors">
              <Trash2 className="w-3.5 h-3.5" />
            </button>
          )}
        </div>
      </div>

      {/* ── Body ── */}
      <div className="flex flex-col flex-1 min-h-0">
        <div className="flex-1 overflow-y-auto px-3 py-2 space-y-2.5 min-h-0">
          {history.length === 0 && !loading && (
            <p className="text-xs text-white italic mt-4 text-center">
              Fragen, Änderungen, Patches — alles möglich.<br />
              <span className="text-gray-700">Auto-Write: sofort anwenden · Kann testen: LLM debuggt selbst</span>
            </p>
          )}
          {history.map((msg, i) => (
            <MessageBubble key={i} msg={msg} autoWrite={autoWrite}
              currentScript={script} currentConfig={configJson}
              onApplyScript={onApplyScript} onApplyConfig={onApplyConfig} />
          ))}
          {loading && (
            <div className="flex justify-start">
              <div className="flex items-center gap-2 rounded-lg px-3 py-1.5 text-xs bg-gray-800 text-white">
                <Loader2 className="w-3 h-3 animate-spin" />
                {canTest ? 'Denkt / testet…' : 'Denkt…'}
              </div>
            </div>
          )}
          {error && <p className="text-xs text-red-400 px-1">{error}</p>}
          <div ref={bottomRef} />
        </div>

        <div className="flex-shrink-0 flex items-end gap-2 px-3 py-2 border-t border-gray-800">
          <textarea ref={inputRef} value={input} onChange={e => setInput(e.target.value)}
            onKeyDown={handleKeyDown} rows={2}
            placeholder="Frage oder Änderungsauftrag… (Enter senden, Shift+Enter Zeilenumbruch)"
            className="flex-1 resize-none bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-xs text-gray-200 placeholder-gray-600 focus:outline-none focus:border-indigo-500"
            disabled={loading} />
          <button type="button" onClick={send} disabled={loading || !input.trim()}
            title="Senden (Enter)"
            className="flex-shrink-0 flex items-center justify-center w-7 h-7 rounded bg-indigo-700 hover:bg-indigo-600 text-white disabled:opacity-40 disabled:cursor-not-allowed transition-colors">
            <CornerDownLeft className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>
    </div>
  )
}
