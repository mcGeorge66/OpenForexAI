/**
 * SystemPromptEditorModal — 3-tab fullscreen editor for an Agent's system_prompt:
 * "Prompt Editor" (line-numbered text), "LLM Assistant" (full-height chat,
 * can pick a specific past analysis + raw snapshot into the discussion),
 * "Agent Context" (per-agent notes file the assistant reads by default).
 *
 * The Prompt Editor tab writes back into the parent form on every keystroke
 * (persisted only when the outer wizard's Save/Update button is clicked —
 * same as every other field) — there is no separate draft here, so it can
 * never go stale relative to the wizard's own inline Prompt tab.
 *
 * The assistant chat and the Agent Context notes state are NOT owned here —
 * both are passed in from the caller (AgentConfigWizard), which also renders
 * its own "LLM Assistant" tab sharing the exact same chat. That's what makes
 * "ask the assistant something" behave identically whether you're in this
 * fullscreen view or the wizard's own tab: one chat, one Agent Context state,
 * rendered in two possible places.
 */
import { useRef, useState } from 'react'
import type React from 'react'
import type { editor as MonacoEditorNS } from 'monaco-editor'
import { Check, Copy, Link2, Loader2, Save, X } from 'lucide-react'
import { PlainTextMonacoEditor } from '@/components/common/PlainTextMonacoEditor'

// The two docs that together cover everything constant across every agent (config field
// names/semantics, full tool parameter schemas) — inserted as [[...]] references, which
// _resolve_file_refs (backend) expands into the assistant's context at chat time. Kept as
// a manual insert rather than auto-injected into every agent's file, so the user decides
// per agent whether/where this shared background belongs in their own notes.
const REFERENCE_LINKS = [
  '[[config/llm_contexts/agent_config_assistant.md]]',
  '[[config/llm_contexts/tools_reference.md]]',
].join('\n')

type Tab = 'prompt' | 'assistant' | 'context'

interface Props {
  agentId: string
  systemPrompt: string
  onChangeSystemPrompt: (text: string) => void
  /** Rendered in the "LLM Assistant" tab — pass a chat driven by shared/lifted
   *  state (the same one rendered in the wizard's own tab) to keep them in sync. */
  assistant: React.ReactNode
  agentContextText: string
  agentContextExists: boolean
  agentContextLoading: boolean
  agentContextSaving: boolean
  agentContextDirty: boolean
  agentContextError: string | null
  onChangeAgentContext: (text: string) => void
  onSaveAgentContext: () => void
  onClose: () => void
}

function CopyButton({ getText }: { getText: () => string }) {
  const [copied, setCopied] = useState(false)
  return (
    <button
      type="button"
      title="Copy to clipboard"
      onClick={() => { void navigator.clipboard.writeText(getText()); setCopied(true); setTimeout(() => setCopied(false), 1500) }}
      className="inline-flex items-center text-gray-500 hover:text-gray-300 transition-colors px-1"
    >
      {copied ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
    </button>
  )
}

export function SystemPromptEditorModal({
  agentId,
  systemPrompt,
  onChangeSystemPrompt,
  assistant,
  agentContextText,
  agentContextExists,
  agentContextLoading,
  agentContextSaving,
  agentContextDirty,
  agentContextError,
  onChangeAgentContext,
  onSaveAgentContext,
  onClose,
}: Props) {
  const [tab, setTab] = useState<Tab>('prompt')
  const contextEditorRef = useRef<MonacoEditorNS.IStandaloneCodeEditor | null>(null)

  const insertReferenceLinks = () => {
    const editor = contextEditorRef.current
    if (!editor) return
    const position = editor.getPosition()
    const range = position
      ? { startLineNumber: position.lineNumber, startColumn: position.column, endLineNumber: position.lineNumber, endColumn: position.column }
      : { startLineNumber: 1, startColumn: 1, endLineNumber: 1, endColumn: 1 }
    editor.executeEdits('insert-reference-links', [{ range, text: REFERENCE_LINKS + '\n', forceMoveMarkers: true }])
    editor.focus()
    onChangeAgentContext(editor.getValue())
  }

  const TAB_LABEL: Record<Tab, string> = {
    prompt: 'Prompt Editor',
    assistant: 'LLM Assistant',
    context: `Agent Context${agentContextDirty ? ' •' : ''}`,
  }

  return (
    <div className="fixed inset-0 z-50 bg-black/70 flex items-center justify-center p-6">
      <div className="w-full max-w-6xl bg-gray-950 border border-gray-700 rounded-xl overflow-hidden flex flex-col" style={{ height: 'calc(100vh - 80px)' }}>
        <div className="px-5 py-3 border-b border-gray-800 flex items-center justify-between flex-shrink-0">
          <div className="flex items-center gap-1">
            {(['prompt', 'assistant', 'context'] as Tab[]).map(t => (
              <button
                key={t}
                onClick={() => setTab(t)}
                className={[
                  'px-3 py-1.5 text-xs rounded transition-colors',
                  tab === t ? 'bg-indigo-700 text-white' : 'text-white hover:text-gray-200 hover:bg-gray-800',
                ].join(' ')}
              >
                {TAB_LABEL[t]}
              </button>
            ))}
          </div>
          <div className="flex items-center gap-2">
            <span className="text-white text-xs font-mono">{agentId}</span>
            <button onClick={onClose} className="text-gray-500 hover:text-gray-300">
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        <div className="flex-1 min-h-0">
          {tab === 'prompt' && (
            <div className="flex flex-col h-full">
              <div className="flex items-center justify-between px-3 py-1.5 bg-gray-900/60 border-b border-gray-800">
                <span className="text-xs text-white">
                  System Prompt · Placeholders <code className="text-gray-300">{'{pair}'}</code>, <code className="text-gray-300">{'{comment}'}</code>
                </span>
                <CopyButton getText={() => systemPrompt} />
              </div>
              <div className="flex-1 min-h-0">
                <PlainTextMonacoEditor value={systemPrompt} onChange={onChangeSystemPrompt} language="plaintext" />
              </div>
            </div>
          )}

          {/* Always mounted (never unmounted on tab switch) so the chat history
              survives switching to Agent Context and back — only hidden via CSS. */}
          <div className={tab === 'assistant' ? 'h-full' : 'hidden'}>
            {assistant}
          </div>

          {tab === 'context' && (
            <div className="flex flex-col h-full">
              <div className="flex items-center justify-between px-3 py-1.5 bg-gray-900/60 border-b border-gray-800">
                <span className="text-xs text-white">
                  config/llm_contexts/{agentId}.md · default context for the LLM Assistant
                  {!agentContextExists && !agentContextLoading && <span className="text-gray-600 italic"> (not created yet)</span>}
                </span>
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={insertReferenceLinks}
                    disabled={agentContextLoading}
                    title="Insert [[...]] references to the shared config-field and tools-reference docs at the cursor"
                    className="flex items-center gap-1 px-2 py-1 text-xs rounded border border-gray-700 text-gray-300 hover:text-white hover:bg-gray-800 disabled:opacity-40 transition-colors"
                  >
                    <Link2 className="w-3 h-3" />
                    Insert reference links
                  </button>
                  <CopyButton getText={() => agentContextText} />
                  <button
                    onClick={onSaveAgentContext}
                    disabled={agentContextSaving || !agentContextDirty}
                    className="flex items-center gap-1 px-2 py-1 text-xs rounded bg-emerald-700 hover:bg-emerald-600 text-white disabled:opacity-40 transition-colors"
                  >
                    {agentContextSaving ? <Loader2 className="w-3 h-3 animate-spin" /> : <Save className="w-3 h-3" />}
                    Save
                  </button>
                </div>
              </div>
              {agentContextError && <div className="px-3 py-1 text-xs text-red-400 bg-red-900/20">{agentContextError}</div>}
              <div className="flex-1 min-h-0">
                {agentContextLoading ? (
                  <div className="flex items-center gap-2 text-white text-xs p-3">
                    <Loader2 className="w-3.5 h-3.5 animate-spin" /> Loading context file…
                  </div>
                ) : (
                  <PlainTextMonacoEditor
                    value={agentContextText}
                    onChange={onChangeAgentContext}
                    language="markdown"
                    onMount={editor => { contextEditorRef.current = editor }}
                  />
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
