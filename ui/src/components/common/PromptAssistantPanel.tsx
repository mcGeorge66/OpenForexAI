/**
 * PromptAssistantPanel — full-height LLM chat view for discussing and rewriting
 * an Agent's system_prompt (and its per-agent context notes file).
 * Purely presentational — all state/logic lives in usePromptAssistantChat (own
 * file, a Fast Refresh requirement: this file must only export the component).
 * Create the chat once with the hook and pass it into as many
 * `<PromptAssistantPanel chat={...} />` renderings as needed — e.g. the Agent
 * Config wizard's own "LLM Assistant" tab AND the fullscreen
 * SystemPromptEditorModal's "LLM Assistant" tab — and both stay in sync since
 * they share one state object.
 *
 * Unlike ScriptAssistantPanel/EntityAssistantPanel, this fills its own tab —
 * the extra room is used for a specific-analysis picker (pull one past
 * decision + its raw snapshot into the discussion, instead of always just
 * "the last one") and opt-in agent-config context.
 *
 * Reuses the exact patch/full-block/diff/tool-call-proposal machinery from
 * assistantShared as-is: target "script" == the System Prompt, target
 * "config" == the Agent Context notes file.
 */
import { useEffect, useRef } from 'react'
import { ArrowLeft, Bot, Check, CornerDownLeft, Loader2, Pencil, Search, Trash2, X } from 'lucide-react'
import type { EntityHistoryEntry } from '@/api/client'
import { MessageBubble } from '@/components/common/MessageBubble'
import type { PromptAssistantChat } from '@/components/common/usePromptAssistantChat'

function summarizeEntry(entry: EntityHistoryEntry): string {
  const out = entry.output as Record<string, unknown> | null
  const bits: string[] = []
  if (out) {
    if (typeof out.symbol === 'string') bits.push(String(out.symbol))
    if (typeof out.decision === 'string') bits.push(String(out.decision))
    else if (typeof out.order_start_signal === 'string') bits.push(String(out.order_start_signal))
    if (typeof out.confidence === 'number') bits.push(`conf ${out.confidence}`)
  }
  const label = bits.length > 0 ? bits.join(' · ') : (entry.trigger ?? '(kein Trigger)')
  return `${entry.timestamp ?? '?'} — ${label}`
}

export function PromptAssistantPanel({ chat }: { chat: PromptAssistantChat }) {
  const {
    history, input, setInput, loading, error,
    autoWrite, setAutoWrite, send, clearChat,
    analysesLoading, analysisFilter, setAnalysisFilter, filteredAnalyses,
    pickerOpen, setPickerOpen, previewEntry, setPreviewEntry,
    selectedAnalysis, setSelectedAnalysis,
    includeSnapshot, setIncludeSnapshot, includeAgentConfig, setIncludeAgentConfig,
    lastInput,
    systemPrompt, agentContextText, onApplySystemPrompt, onApplyAgentContext,
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
    <div className="flex flex-col h-full">
      {/* ── Context controls ── */}
      <div className="flex-shrink-0 border-b border-gray-700 bg-gray-950/60">
        <div className="px-3 py-2 space-y-2">
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => { setPickerOpen(v => !v); setPreviewEntry(null) }}
              className="flex items-center gap-1.5 text-xs text-gray-300 hover:text-white bg-gray-800 border border-gray-700 rounded px-2 py-1 transition-colors"
            >
              <Search className="w-3.5 h-3.5" />
              {selectedAnalysis ? 'Change analysis' : 'Select analysis'}
            </button>
            {selectedAnalysis && (
              <span className="flex items-center gap-1.5 text-xs text-emerald-300 bg-emerald-900/20 border border-emerald-800/50 rounded px-2 py-1 max-w-md truncate">
                {summarizeEntry(selectedAnalysis)}
                <button type="button" onClick={() => setSelectedAnalysis(null)} title="Remove selection">
                  <X className="w-3 h-3 text-emerald-400 hover:text-emerald-200" />
                </button>
              </span>
            )}
          </div>

          {pickerOpen && previewEntry && (
            <div className="border border-indigo-800/60 rounded bg-gray-900 p-2 space-y-2">
              <div className="flex items-center justify-between">
                <button
                  type="button"
                  onClick={() => setPreviewEntry(null)}
                  className="flex items-center gap-1 text-xs text-white hover:text-gray-200 transition-colors"
                >
                  <ArrowLeft className="w-3.5 h-3.5" />
                  Back
                </button>
                <span className="text-xs text-white">{previewEntry.timestamp ?? ''}</span>
              </div>
              <pre className="text-xs text-gray-300 bg-gray-950 rounded p-2 overflow-auto max-h-64 font-mono whitespace-pre-wrap break-all">
                {previewEntry.output !== null ? JSON.stringify(previewEntry.output, null, 2) : '(no output)'}
              </pre>
              <button
                type="button"
                onClick={() => { setSelectedAnalysis(previewEntry); setPreviewEntry(null); setPickerOpen(false) }}
                className="w-full flex items-center justify-center gap-1.5 text-xs text-white bg-indigo-700 hover:bg-indigo-600 rounded px-2 py-1.5 transition-colors"
              >
                <Check className="w-3.5 h-3.5" />
                Use this analysis
              </button>
            </div>
          )}

          {pickerOpen && !previewEntry && (
            <div className="border border-gray-700 rounded bg-gray-900 p-2 space-y-2">
              <input
                value={analysisFilter}
                onChange={e => setAnalysisFilter(e.target.value)}
                placeholder="Filter by timestamp, symbol, decision…"
                className="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1 text-xs text-gray-200 focus:outline-none focus:border-indigo-500"
              />
              <div className="max-h-40 overflow-y-auto space-y-1">
                {analysesLoading && (
                  <div className="flex items-center gap-2 text-white text-xs px-1">
                    <Loader2 className="w-3 h-3 animate-spin" /> Loading analyses…
                  </div>
                )}
                {!analysesLoading && filteredAnalyses.length === 0 && (
                  <p className="text-xs text-white italic px-1">No analyses found.</p>
                )}
                {filteredAnalyses.map(entry => (
                  <button
                    key={entry.id}
                    type="button"
                    onClick={() => setPreviewEntry(entry)}
                    className="w-full text-left text-xs text-gray-300 hover:bg-gray-800 rounded px-2 py-1 truncate transition-colors"
                    title={summarizeEntry(entry)}
                  >
                    {summarizeEntry(entry)}
                  </button>
                ))}
              </div>
            </div>
          )}

          <div className="flex items-center gap-4 text-[11px]">
            <label className="flex items-center gap-1.5 cursor-pointer select-none text-gray-400">
              <input
                type="checkbox"
                checked={includeSnapshot}
                disabled={!selectedAnalysis}
                onChange={e => setIncludeSnapshot(e.target.checked)}
                className="accent-emerald-600"
              />
              Include raw snapshot data
            </label>
            <label className="flex items-center gap-1.5 cursor-pointer select-none text-gray-400">
              <input
                type="checkbox"
                checked={includeAgentConfig}
                onChange={e => setIncludeAgentConfig(e.target.checked)}
                className="accent-emerald-600"
              />
              Include agent configuration
            </label>
            <span
              className={lastInput?.available ? 'text-emerald-400' : 'text-gray-600'}
              title={
                lastInput?.available
                  ? `Zuletzt empfangener Input (${lastInput.timestamp}, Trigger: ${lastInput.trigger}) wird automatisch mitgegeben`
                  : 'Dieser Agent hat seit dem letzten Start noch keinen Zyklus verarbeitet — kein Input verfügbar'
              }
            >
              {lastInput?.available ? '✓ Last input included' : '(no last input yet)'}
            </span>

            <label className="flex items-center gap-1.5 cursor-pointer select-none ml-auto"
              title="Apply code blocks and patches to Prompt/Context immediately">
              <div onClick={() => setAutoWrite(v => !v)}
                className={['relative w-7 h-4 rounded-full transition-colors cursor-pointer', autoWrite ? 'bg-emerald-600' : 'bg-gray-700'].join(' ')}>
                <div className={['absolute top-0.5 w-3 h-3 rounded-full bg-white transition-transform', autoWrite ? 'translate-x-3.5' : 'translate-x-0.5'].join(' ')} />
              </div>
              <Pencil className="w-3 h-3 text-gray-500" />
              <span className={autoWrite ? 'text-emerald-400' : 'text-gray-600'}>Auto-Write</span>
            </label>

            {history.length > 0 && (
              <button type="button" onClick={clearChat}
                title="Clear chat" className="text-gray-600 hover:text-red-400 transition-colors">
                <Trash2 className="w-3.5 h-3.5" />
              </button>
            )}
          </div>
        </div>
      </div>

      {/* ── Chat body ── */}
      <div className="flex-1 overflow-y-auto px-3 py-3 space-y-2.5 min-h-0">
        {history.length === 0 && !loading && (
          <p className="text-xs text-white italic mt-4 text-center">
            <Bot className="w-5 h-5 mx-auto mb-2 text-indigo-500" />
            Discuss the system prompt, optionally pick a specific analysis.<br />
            <span className="text-gray-700">Auto-Write: apply changes immediately</span>
          </p>
        )}
        {history.map((msg, i) => (
          <MessageBubble key={i} msg={msg} autoWrite={autoWrite}
            currentScript={systemPrompt} currentConfig={agentContextText}
            onApplyScript={onApplySystemPrompt} onApplyConfig={onApplyAgentContext} />
        ))}
        {loading && (
          <div className="flex justify-start">
            <div className="flex items-center gap-2 rounded-lg px-3 py-1.5 text-xs bg-gray-800 text-white">
              <Loader2 className="w-3 h-3 animate-spin" />
              Thinking…
            </div>
          </div>
        )}
        {error && <p className="text-xs text-red-400 px-1">{error}</p>}
        <div ref={bottomRef} />
      </div>

      {/* ── Input ── */}
      <div className="flex-shrink-0 flex items-end gap-2 px-3 py-2 border-t border-gray-800">
        <textarea ref={inputRef} value={input} onChange={e => setInput(e.target.value)}
          onKeyDown={handleKeyDown} rows={2}
          placeholder="Question or change request… (Enter to send, Shift+Enter for newline)"
          className="flex-1 resize-none bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-xs text-gray-200 placeholder-gray-600 focus:outline-none focus:border-indigo-500"
          disabled={loading} />
        <button type="button" onClick={send} disabled={loading || !input.trim()}
          title="Senden (Enter)"
          className="flex-shrink-0 flex items-center justify-center w-7 h-7 rounded bg-indigo-700 hover:bg-indigo-600 text-white disabled:opacity-40 disabled:cursor-not-allowed transition-colors">
          <CornerDownLeft className="w-3.5 h-3.5" />
        </button>
      </div>
    </div>
  )
}
