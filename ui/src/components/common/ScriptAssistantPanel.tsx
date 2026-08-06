/**
 * ScriptAssistantPanel — resizable LLM chat panel for the fullscreen ScriptEditor modal.
 *
 * Replaces the old read-only LLMChatPanel with full patch/write capabilities:
 *   - Full script replacement via ```python blocks
 *   - Line-number patches: <<<PATCH SCRIPT L5-L10>>> ... <<<END>>>
 *   - Insert: <<<INSERT SCRIPT AFTER L10>>> ... <<<END>>>
 *   - Auto-Write toggle: apply changes immediately without confirmation
 *
 * The panel is rendered below the Monaco editor and is resizable via a drag handle
 * in the parent (ExpandedEditorModal passes `height` as a prop).
 */

import React, { useEffect, useRef, useState } from 'react'
import { Bot, ChevronDown, ChevronUp, CornerDownLeft, Loader2, Pencil, Trash2 } from 'lucide-react'
import { api } from '@/api/client'
import {
  applyPatch,
  parseResponse,
  type AssistantMessage,
  type ParsedResponse,
} from '@/components/common/assistantShared'
import { MessageBubble } from '@/components/common/MessageBubble'

// ─── Types ────────────────────────────────────────────────────────────────────

export interface ScriptAssistantPanelProps {
  code: string
  contextFile: string
  onApplyCode: (code: string) => void
  /** Additional context passed to the LLM (e.g. tool name + arguments for transform scripts) */
  contextData?: string
  /** Panel body height in px (controlled by drag handle in parent) */
  height?: number
  /** Start open */
  initialOpen?: boolean
}

// ─── Component ────────────────────────────────────────────────────────────────

export function ScriptAssistantPanel({
  code,
  contextFile,
  onApplyCode,
  contextData,
  height = 280,
  initialOpen = false,
}: ScriptAssistantPanelProps) {
  const [open, setOpen] = useState(initialOpen)
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [autoWrite, setAutoWrite] = useState(false)
  const [history, setHistory] = useState<AssistantMessage[]>([])

  const bottomRef = useRef<HTMLDivElement | null>(null)
  const inputRef = useRef<HTMLTextAreaElement | null>(null)
  const historyRef = useRef(history)
  historyRef.current = history

  const codeRef = useRef(code); codeRef.current = code
  const autoWriteRef = useRef(autoWrite); autoWriteRef.current = autoWrite
  const onApplyCodeRef = useRef(onApplyCode); onApplyCodeRef.current = onApplyCode

  useEffect(() => {
    if (open) bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [history, open])

  useEffect(() => {
    if (open) setTimeout(() => inputRef.current?.focus(), 50)
  }, [open])

  function buildContextData(): string {
    const lines = codeRef.current.split('\n')
    const numbered = lines.map((l, i) => `${String(i + 1).padStart(4, ' ')} | ${l}`).join('\n')
    const parts = [`=== Script (Python, with line numbers) ===\n\`\`\`\n${numbered}\n\`\`\``]
    if (contextData) parts.push(contextData)
    return parts.join('\n\n')
  }

  function appendMessage(msg: AssistantMessage) {
    setHistory(h => [...h, msg])
  }

  function autoApplyParsed(parsed: ParsedResponse) {
    for (const seg of parsed.segments) {
      if (seg.type === 'full' && seg.block.target === 'script') {
        onApplyCodeRef.current(seg.block.code)
      }
      if (seg.type === 'patch' && seg.block.target === 'script') {
        const { result } = applyPatch(codeRef.current, seg.block)
        onApplyCodeRef.current(result)
      }
    }
  }

  async function send(): Promise<void> {
    const question = input.trim()
    if (!question || loading) return
    appendMessage({ role: 'user', content: question })
    setInput('')
    setLoading(true)
    setError(null)
    try {
      const resp = await api.llmAssistantChat({
        context_file: contextFile,
        script: codeRef.current,
        question,
        history: historyRef.current.map(({ role, content }) => ({ role, content })),
        context_data: buildContextData(),
      })
      if (resp.error) { setError(resp.error); return }
      const parsed = parseResponse(resp.answer)
      if (autoWriteRef.current) autoApplyParsed(parsed)
      appendMessage({ role: 'assistant', content: resp.answer, parsed })
    } catch (e: unknown) {
      setError(String(e))
    } finally {
      setLoading(false)
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); void send() }
  }

  return (
    <div className="flex-shrink-0 border-t border-gray-700 bg-gray-950">
      {/* ── Toggle header ── */}
      <div className="flex items-center gap-2 px-3 py-2 select-none">
        <button type="button" onClick={() => setOpen(v => !v)}
          className="flex items-center gap-2 flex-1 text-xs text-white hover:text-gray-200 transition-colors">
          <Bot className="w-3.5 h-3.5 flex-shrink-0 text-indigo-400" />
          <span className="font-medium text-left flex-1">Script Assistant</span>
          {open ? <ChevronDown className="w-3.5 h-3.5 flex-shrink-0" /> : <ChevronUp className="w-3.5 h-3.5 flex-shrink-0" />}
        </button>

        <div className="flex items-center gap-3 text-[11px]">
          <label className="flex items-center gap-1.5 cursor-pointer select-none"
            title="Code-Blöcke und Patches sofort in den Editor übernehmen">
            <div onClick={() => setAutoWrite(v => !v)}
              className={['relative w-7 h-4 rounded-full transition-colors cursor-pointer', autoWrite ? 'bg-emerald-600' : 'bg-gray-700'].join(' ')}>
              <div className={['absolute top-0.5 w-3 h-3 rounded-full bg-white transition-transform', autoWrite ? 'translate-x-3.5' : 'translate-x-0.5'].join(' ')} />
            </div>
            <Pencil className="w-3 h-3 text-gray-500" />
            <span className={autoWrite ? 'text-emerald-400' : 'text-gray-600'}>Auto-Write</span>
          </label>

          {history.length > 0 && (
            <button type="button" onClick={() => { setHistory([]); setError(null) }}
              title="Chat leeren" className="text-gray-600 hover:text-red-400 transition-colors">
              <Trash2 className="w-3.5 h-3.5" />
            </button>
          )}
        </div>
      </div>

      {/* ── Body ── */}
      {open && (
        <div className="flex flex-col border-t border-gray-700" style={{ height: `${height}px` }}>
          <div className="flex-1 overflow-y-auto px-3 py-2 space-y-2.5 min-h-0">
            {history.length === 0 && !loading && (
              <p className="text-xs text-white italic mt-4 text-center">
                Fragen zum Script, Änderungen, Patches — alles möglich.<br />
                <span className="text-gray-700">Auto-Write: Änderungen sofort in den Editor übernehmen</span>
              </p>
            )}
            {history.map((msg, i) => (
              <MessageBubble key={i} msg={msg} autoWrite={autoWrite}
                currentScript={code}
                onApplyScript={onApplyCode} />
            ))}
            {loading && (
              <div className="flex justify-start">
                <div className="flex items-center gap-2 rounded-lg px-3 py-1.5 text-xs bg-gray-800 text-white">
                  <Loader2 className="w-3 h-3 animate-spin" />
                  Denkt…
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
            <button type="button" onClick={() => void send()} disabled={loading || !input.trim()}
              title="Senden (Enter)"
              className="flex-shrink-0 flex items-center justify-center w-7 h-7 rounded bg-indigo-700 hover:bg-indigo-600 text-white disabled:opacity-40 disabled:cursor-not-allowed transition-colors">
              <CornerDownLeft className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
