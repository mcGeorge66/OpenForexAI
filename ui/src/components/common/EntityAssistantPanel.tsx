/**
 * EntityAssistantPanel — collapsible LLM chat for EventComposer entities.
 *
 * Supports full script/config replacement, line-number patches, and an
 * agentic debug loop (auto-test + auto-fix up to MAX_AUTO_ITERATIONS).
 *
 * Patch formats (see entity_config_assistant.md for full docs):
 *   <<<PATCH SCRIPT L12-L18>>>  /  <<<PATCH CONFIG L3>>>  /  <<<INSERT SCRIPT AFTER L10>>>
 *   <<<END>>>
 */

import React, { useEffect, useRef, useState } from 'react'
import { Bot, ChevronDown, ChevronUp, CornerDownLeft, Loader2, Pencil, FlaskConical, Trash2 } from 'lucide-react'
import { api, type ECExecuteResponse } from '@/api/client'
import {
  applyPatch,
  parseResponse,
  MessageBubble,
  type AssistantMessage,
  type ParsedResponse,
} from '@/components/common/assistantShared'

// ─── Types ────────────────────────────────────────────────────────────────────

export interface EntityAssistantPanelProps {
  script: string
  configJson: string
  allowedTools: string[]
  testInput: string
  testResult: ECExecuteResponse | null
  contextFile?: string
  onApplyScript: (code: string) => void
  onApplyConfig: (json: string) => void
  onRunTest: () => Promise<ECExecuteResponse | null>
}

const MAX_AUTO_ITERATIONS = 5
const CONTEXT_FILE_DEFAULT = 'entity_config_assistant.md'

// ─── Component ────────────────────────────────────────────────────────────────

export function EntityAssistantPanel({
  script,
  configJson,
  allowedTools,
  testInput,
  testResult,
  contextFile = CONTEXT_FILE_DEFAULT,
  onApplyScript,
  onApplyConfig,
  onRunTest,
}: EntityAssistantPanelProps) {
  const [open, setOpen] = useState(false)
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [autoWrite, setAutoWrite] = useState(false)
  const [canTest, setCanTest] = useState(false)
  const [history, setHistory] = useState<AssistantMessage[]>([])

  const bottomRef = useRef<HTMLDivElement | null>(null)
  const inputRef = useRef<HTMLTextAreaElement | null>(null)
  const historyRef = useRef(history)
  historyRef.current = history

  const scriptRef = useRef(script); scriptRef.current = script
  const configJsonRef = useRef(configJson); configJsonRef.current = configJson
  const testInputRef = useRef(testInput); testInputRef.current = testInput
  const autoWriteRef = useRef(autoWrite); autoWriteRef.current = autoWrite
  const canTestRef = useRef(canTest); canTestRef.current = canTest
  const onApplyScriptRef = useRef(onApplyScript); onApplyScriptRef.current = onApplyScript
  const onApplyConfigRef = useRef(onApplyConfig); onApplyConfigRef.current = onApplyConfig
  const onRunTestRef = useRef(onRunTest); onRunTestRef.current = onRunTest

  useEffect(() => {
    if (open) bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [history, open])

  useEffect(() => {
    if (open) setTimeout(() => inputRef.current?.focus(), 50)
  }, [open])

  function buildContextData(lastResult?: ECExecuteResponse | null): string {
    const lines = scriptRef.current.split('\n')
    const numbered = lines.map((l, i) => `${String(i + 1).padStart(4, ' ')} | ${l}`).join('\n')
    const parts = [
      `=== Script (Python, with line numbers) ===\n\`\`\`\n${numbered}\n\`\`\``,
      `=== Config JSON ===\n\`\`\`json\n${configJsonRef.current}\n\`\`\``,
      `=== Allowed Tools ===\n${allowedTools.length ? allowedTools.join(', ') : '(none)'}`,
    ]
    const ti = testInputRef.current?.trim()
    if (ti) parts.push(`=== Test Input ===\n\`\`\`json\n${ti}\n\`\`\``)
    const lr = lastResult ?? testResult
    if (lr) parts.push(`=== Last Test Result ===\n\`\`\`json\n${JSON.stringify(lr, null, 2)}\n\`\`\``)
    return parts.join('\n\n')
  }

  function appendMessage(msg: AssistantMessage) {
    setHistory(h => [...h, msg])
  }

  function autoApplyParsed(parsed: ParsedResponse) {
    for (const seg of parsed.segments) {
      if (seg.type === 'full') {
        if (seg.block.target === 'script') onApplyScriptRef.current(seg.block.code)
        if (seg.block.target === 'config') onApplyConfigRef.current(seg.block.code)
      }
      if (seg.type === 'patch') {
        const source = seg.block.target === 'script' ? scriptRef.current : configJsonRef.current
        const { result } = applyPatch(source, seg.block)
        if (seg.block.target === 'script') onApplyScriptRef.current(result)
        if (seg.block.target === 'config') onApplyConfigRef.current(result)
      }
    }
  }

  async function runAgentLoop(question: string, iteration = 0): Promise<void> {
    if (iteration >= MAX_AUTO_ITERATIONS) {
      appendMessage({ role: 'assistant', content: `⚠️ Maximale Iterationsanzahl (${MAX_AUTO_ITERATIONS}) erreicht.` })
      return
    }
    setLoading(true)
    setError(null)
    try {
      const resp = await api.llmAssistantChat({
        context_file: contextFile,
        script: scriptRef.current,
        question,
        history: historyRef.current.map(({ role, content }) => ({ role, content })),
        context_data: buildContextData(),
      })
      if (resp.error) { setError(resp.error); setLoading(false); return }

      const parsed = parseResponse(resp.answer)
      if (autoWriteRef.current) autoApplyParsed(parsed)
      appendMessage({ role: 'assistant', content: resp.answer, parsed })

      if (parsed.triggerRun && canTestRef.current) {
        setLoading(false)
        await new Promise(r => setTimeout(r, 400))
        let runResult: ECExecuteResponse | null = null
        try { runResult = await onRunTestRef.current() } catch { /* non-fatal */ }
        const resultSummary = runResult
          ? `Test-Ergebnis:\n\`\`\`json\n${JSON.stringify(runResult, null, 2)}\n\`\`\``
          : 'Test konnte nicht ausgeführt werden.'
        const followUp = `[Automatisches Test-Feedback, Iteration ${iteration + 1}]\n${resultSummary}`
        appendMessage({ role: 'user', content: followUp })
        if (runResult && !runResult.success) { await runAgentLoop(followUp, iteration + 1); return }
        setLoading(false)
        return
      }
    } catch (e: unknown) {
      setError(String(e))
    } finally {
      setLoading(false)
    }
  }

  const send = async () => {
    const question = input.trim()
    if (!question || loading) return
    appendMessage({ role: 'user', content: question })
    setInput('')
    await runAgentLoop(question)
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); void send() }
  }

  return (
    <div className="flex-shrink-0 border border-gray-700 rounded bg-gray-950">
      {/* ── Header ── */}
      <div className="flex items-center gap-2 px-3 py-2 select-none">
        <button type="button" onClick={() => setOpen(v => !v)}
          className="flex items-center gap-2 flex-1 text-xs text-gray-400 hover:text-gray-200 transition-colors">
          <Bot className="w-3.5 h-3.5 flex-shrink-0 text-indigo-400" />
          <span className="font-medium text-left flex-1">Entity Assistant</span>
          {open ? <ChevronDown className="w-3.5 h-3.5 flex-shrink-0" /> : <ChevronUp className="w-3.5 h-3.5 flex-shrink-0" />}
        </button>

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
            <button type="button" onClick={() => { setHistory([]); setError(null) }}
              title="Chat leeren" className="text-gray-600 hover:text-red-400 transition-colors">
              <Trash2 className="w-3.5 h-3.5" />
            </button>
          )}
        </div>
      </div>

      {/* ── Body ── */}
      {open && (
        <div className="flex flex-col border-t border-gray-700" style={{ height: 380 }}>
          <div className="flex-1 overflow-y-auto px-3 py-2 space-y-2.5 min-h-0">
            {history.length === 0 && !loading && (
              <p className="text-xs text-gray-600 italic mt-4 text-center">
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
                <div className="flex items-center gap-2 rounded-lg px-3 py-1.5 text-xs bg-gray-800 text-gray-400">
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
