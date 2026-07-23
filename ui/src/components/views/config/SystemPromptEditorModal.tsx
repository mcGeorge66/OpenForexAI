/**
 * SystemPromptEditorModal — 3-tab editor for an Agent's system_prompt:
 * "Prompt Editor" (line-numbered text), "LLM Assistant" (full-height chat,
 * can pick a specific past analysis + raw snapshot into the discussion),
 * "Agent Context" (per-agent notes file the assistant reads by default).
 *
 * The Prompt Editor tab writes back into the parent form (persisted only
 * when the outer wizard's Save/Update button is clicked — same as every
 * other field). The Agent Context tab is a separate file on disk and saves
 * itself via its own Save button.
 */
import { useEffect, useState } from 'react'
import { Check, Copy, Loader2, Save, X } from 'lucide-react'
import { api } from '@/api/client'
import { PlainTextMonacoEditor } from '@/components/common/PlainTextMonacoEditor'
import { PromptAssistantPanel, type AgentConfigSummary } from '@/components/common/PromptAssistantPanel'

type Tab = 'prompt' | 'assistant' | 'context'

interface Props {
  agentConfig: AgentConfigSummary
  systemPrompt: string
  onChangeSystemPrompt: (text: string) => void
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

export function SystemPromptEditorModal({ agentConfig, systemPrompt, onChangeSystemPrompt, onClose }: Props) {
  const agentId = agentConfig.agent_id
  const [tab, setTab] = useState<Tab>('prompt')

  const [contextText, setContextText] = useState('')
  const [contextExists, setContextExists] = useState(false)
  const [contextLoading, setContextLoading] = useState(true)
  const [contextSaving, setContextSaving] = useState(false)
  const [contextSavedText, setContextSavedText] = useState('')
  const [contextError, setContextError] = useState<string | null>(null)

  useEffect(() => {
    setContextLoading(true)
    api.getAgentContext(agentId)
      .then(resp => {
        setContextText(resp.text)
        setContextSavedText(resp.text)
        setContextExists(resp.exists)
      })
      .catch(e => setContextError(String(e)))
      .finally(() => setContextLoading(false))
  }, [agentId])

  const contextDirty = contextText !== contextSavedText

  async function saveContext() {
    setContextSaving(true)
    setContextError(null)
    try {
      await api.saveAgentContext(agentId, contextText)
      setContextSavedText(contextText)
      setContextExists(true)
    } catch (e) {
      setContextError(String(e))
    } finally {
      setContextSaving(false)
    }
  }

  const TAB_LABEL: Record<Tab, string> = {
    prompt: 'Prompt Editor',
    assistant: 'LLM Assistant',
    context: `Agent Context${contextDirty ? ' •' : ''}`,
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
            <PromptAssistantPanel
              agentId={agentId}
              systemPrompt={systemPrompt}
              onApplySystemPrompt={onChangeSystemPrompt}
              agentContextText={contextText}
              agentContextExists={contextExists}
              onApplyAgentContext={setContextText}
              agentConfig={agentConfig}
            />
          </div>

          {tab === 'context' && (
            <div className="flex flex-col h-full">
              <div className="flex items-center justify-between px-3 py-1.5 bg-gray-900/60 border-b border-gray-800">
                <span className="text-xs text-white">
                  config/llm_contexts/{agentId}.md · default context for the LLM Assistant
                  {!contextExists && !contextLoading && <span className="text-gray-600 italic"> (not created yet)</span>}
                </span>
                <div className="flex items-center gap-2">
                  <CopyButton getText={() => contextText} />
                  <button
                    onClick={() => void saveContext()}
                    disabled={contextSaving || !contextDirty}
                    className="flex items-center gap-1 px-2 py-1 text-xs rounded bg-emerald-700 hover:bg-emerald-600 text-white disabled:opacity-40 transition-colors"
                  >
                    {contextSaving ? <Loader2 className="w-3 h-3 animate-spin" /> : <Save className="w-3 h-3" />}
                    Save
                  </button>
                </div>
              </div>
              {contextError && <div className="px-3 py-1 text-xs text-red-400 bg-red-900/20">{contextError}</div>}
              <div className="flex-1 min-h-0">
                {contextLoading ? (
                  <div className="flex items-center gap-2 text-white text-xs p-3">
                    <Loader2 className="w-3.5 h-3.5 animate-spin" /> Loading context file…
                  </div>
                ) : (
                  <PlainTextMonacoEditor value={contextText} onChange={setContextText} language="markdown" />
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
