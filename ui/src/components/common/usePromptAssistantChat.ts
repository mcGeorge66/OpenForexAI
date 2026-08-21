/**
 * usePromptAssistantChat — state/logic for the Agent system_prompt assistant.
 * Split out of PromptAssistantPanel.tsx (a Fast Refresh requirement: that file
 * must only export the component).
 *
 * Create ONE instance per agent being edited and pass its return value into
 * as many `<PromptAssistantPanel chat={...} />` renderings as needed — e.g.
 * the Agent Config wizard's own "LLM Assistant" tab AND the fullscreen
 * SystemPromptEditorModal's "LLM Assistant" tab — both stay in sync since
 * they share this one state object instead of each owning a disconnected copy.
 */

import { useEffect, useMemo, useRef, useState, type Dispatch, type SetStateAction } from 'react'
import { api, type AgentLastInputResponse, type EntityHistoryEntry } from '@/api/client'
import {
  applyDiffHunk,
  applyPatch,
  buildParsedResponse,
  type AssistantMessage,
  type ParsedResponse,
} from '@/components/common/assistantShared'

export interface AgentConfigSummary {
  agent_id: string
  pair?: string
  broker?: string
  snapshot_profile?: string
  decision_prompt_profile?: string
  event_triggers?: string[]
  allowed_tools?: string[]
}

export interface PromptAssistantPanelProps {
  agentId: string
  systemPrompt: string
  onApplySystemPrompt: (text: string) => void
  agentContextText: string
  agentContextExists: boolean
  onApplyAgentContext: (text: string) => void
  agentConfig: AgentConfigSummary
}

export interface PromptAssistantChat {
  history: AssistantMessage[]
  input: string
  setInput: (v: string) => void
  loading: boolean
  error: string | null
  autoWrite: boolean
  setAutoWrite: Dispatch<SetStateAction<boolean>>
  send: () => void
  clearChat: () => void

  analyses: EntityHistoryEntry[]
  analysesLoading: boolean
  analysisFilter: string
  setAnalysisFilter: (v: string) => void
  filteredAnalyses: EntityHistoryEntry[]
  pickerOpen: boolean
  setPickerOpen: Dispatch<SetStateAction<boolean>>
  previewEntry: EntityHistoryEntry | null
  setPreviewEntry: (v: EntityHistoryEntry | null) => void
  selectedAnalysis: EntityHistoryEntry | null
  setSelectedAnalysis: (v: EntityHistoryEntry | null) => void
  includeSnapshot: boolean
  setIncludeSnapshot: Dispatch<SetStateAction<boolean>>
  includeAgentConfig: boolean
  setIncludeAgentConfig: Dispatch<SetStateAction<boolean>>
  lastInput: AgentLastInputResponse | null

  systemPrompt: string
  agentContextText: string
  onApplySystemPrompt: (text: string) => void
  onApplyAgentContext: (text: string) => void
}

const CONTEXT_FILE = 'prompt_assistant.md'

function numbered(text: string): string {
  if (!text.trim()) return '(empty)'
  return text.split('\n').map((l, i) => `${String(i + 1).padStart(4, ' ')} | ${l}`).join('\n')
}

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

function extractSnapshot(entry: EntityHistoryEntry): Record<string, unknown> | null {
  const input = entry.input as Record<string, unknown> | null
  const snap = input?.market_snapshot
  return snap && typeof snap === 'object' ? (snap as Record<string, unknown>) : null
}

export function usePromptAssistantChat({
  agentId,
  systemPrompt,
  onApplySystemPrompt,
  agentContextText,
  agentContextExists,
  onApplyAgentContext,
  agentConfig,
}: PromptAssistantPanelProps): PromptAssistantChat {
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [autoWrite, setAutoWrite] = useState(false)
  const [history, setHistory] = useState<AssistantMessage[]>([])

  const [analyses, setAnalyses] = useState<EntityHistoryEntry[]>([])
  const [analysesLoading, setAnalysesLoading] = useState(false)
  const [analysisFilter, setAnalysisFilter] = useState('')
  const [pickerOpen, setPickerOpen] = useState(false)
  const [previewEntry, setPreviewEntry] = useState<EntityHistoryEntry | null>(null)
  const [selectedAnalysis, setSelectedAnalysis] = useState<EntityHistoryEntry | null>(null)
  const [includeSnapshot, setIncludeSnapshot] = useState(true)
  const [includeAgentConfig, setIncludeAgentConfig] = useState(false)
  const [lastInput, setLastInput] = useState<AgentLastInputResponse | null>(null)

  const historyRef = useRef(history); historyRef.current = history
  const systemPromptRef = useRef(systemPrompt); systemPromptRef.current = systemPrompt
  const agentContextRef = useRef(agentContextText); agentContextRef.current = agentContextText
  const autoWriteRef = useRef(autoWrite); autoWriteRef.current = autoWrite
  const onApplySystemPromptRef = useRef(onApplySystemPrompt); onApplySystemPromptRef.current = onApplySystemPrompt
  const onApplyAgentContextRef = useRef(onApplyAgentContext); onApplyAgentContextRef.current = onApplyAgentContext

  useEffect(() => {
    setAnalysesLoading(true)
    api.getEntityHistory('agent', agentId, 50)
      .then(setAnalyses)
      .catch(() => setAnalyses([]))
      .finally(() => setAnalysesLoading(false))
  }, [agentId])

  // Live, in-RAM-only on the backend — whatever this agent (AA/BA/GA) most recently
  // actually received, e.g. a BA's upstream AA output. Always mixed into the LLM's
  // context below (not opt-in) so prompt/output-format mismatches surface immediately.
  useEffect(() => {
    api.getAgentLastInput(agentId)
      .then(setLastInput)
      .catch(() => setLastInput(null))
  }, [agentId])

  const filteredAnalyses = useMemo(() => {
    const q = analysisFilter.trim().toLowerCase()
    if (!q) return analyses
    return analyses.filter(a =>
      summarizeEntry(a).toLowerCase().includes(q) || (a.timestamp ?? '').toLowerCase().includes(q),
    )
  }, [analyses, analysisFilter])

  function buildContextData(): string {
    const parts = [
      `=== System Prompt (with line numbers) ===\n${numbered(systemPromptRef.current)}`,
    ]
    if (agentContextExists || agentContextRef.current.trim()) {
      parts.push(`=== Agent Context Notes (config/llm_contexts/${agentId}.md, with line numbers) ===\n${numbered(agentContextRef.current)}`)
    } else {
      parts.push('=== Agent Context Notes ===\n(no notes file yet for this agent)')
    }
    if (includeAgentConfig) {
      parts.push(`=== Agent Configuration ===\n\`\`\`json\n${JSON.stringify(agentConfig, null, 2)}\n\`\`\``)
    }
    if (lastInput?.available) {
      parts.push(
        `=== Last Received Input (live, ${lastInput.timestamp ?? '?'}) ===\n` +
        `The exact text this agent's LLM most recently received as its user message — check whether ` +
        `the prompt above actually handles/expects this, e.g. field names it references.\n` +
        `Trigger: ${lastInput.trigger ?? '(unknown)'} · Source: ${lastInput.source ?? '(unknown)'}\n` +
        (lastInput.user_message ?? '(empty)'),
      )
    }
    if (selectedAnalysis) {
      parts.push(
        `=== Selected Analysis (${selectedAnalysis.timestamp ?? '?'}) ===\n` +
        `Trigger: ${selectedAnalysis.trigger ?? '(unknown)'}\n` +
        `\`\`\`json\n${JSON.stringify(selectedAnalysis.output, null, 2)}\n\`\`\``,
      )
      if (includeSnapshot) {
        const snap = extractSnapshot(selectedAnalysis)
        parts.push(
          snap
            ? `=== Raw Snapshot Data For Selected Analysis ===\n\`\`\`json\n${JSON.stringify(snap, null, 2)}\n\`\`\``
            : '=== Raw Snapshot Data For Selected Analysis ===\n(not available for this entry)',
        )
      }
    }
    return parts.join('\n\n')
  }

  function appendMessage(msg: AssistantMessage) {
    setHistory(h => [...h, msg])
  }

  function autoApplyParsed(parsed: ParsedResponse) {
    for (const seg of parsed.segments) {
      if (seg.type === 'full') {
        if (seg.block.target === 'script') onApplySystemPromptRef.current(seg.block.code)
        if (seg.block.target === 'config') onApplyAgentContextRef.current(seg.block.code)
      }
      if (seg.type === 'patch') {
        const source = seg.block.target === 'script' ? systemPromptRef.current : agentContextRef.current
        const { result } = applyPatch(source, seg.block)
        if (seg.block.target === 'script') onApplySystemPromptRef.current(result)
        if (seg.block.target === 'config') onApplyAgentContextRef.current(result)
      }
      if (seg.type === 'diffhunk') {
        const source = seg.block.target === 'script' ? systemPromptRef.current : agentContextRef.current
        const { result, error: applyError } = applyDiffHunk(source, seg.block)
        if (!applyError) {
          if (seg.block.target === 'script') onApplySystemPromptRef.current(result)
          if (seg.block.target === 'config') onApplyAgentContextRef.current(result)
        }
      }
    }
  }

  async function runSend(): Promise<void> {
    const question = input.trim()
    if (!question || loading) return
    appendMessage({ role: 'user', content: question })
    setInput('')
    setLoading(true)
    setError(null)
    try {
      const resp = await api.llmAssistantChat({
        context_file: CONTEXT_FILE,
        script: systemPromptRef.current,
        question,
        history: historyRef.current.map(({ role, content }) => ({ role, content })),
        context_data: buildContextData(),
        allow_change_proposals: true,
      })
      if (resp.error) { setError(resp.error); return }
      const parsed = buildParsedResponse(resp.answer, resp.proposals)
      if (autoWriteRef.current) autoApplyParsed(parsed)
      appendMessage({ role: 'assistant', content: resp.answer, parsed })
    } catch (e: unknown) {
      setError(String(e))
    } finally {
      setLoading(false)
    }
  }

  const send = () => { void runSend() }
  const clearChat = () => { setHistory([]); setError(null) }

  return {
    history, input, setInput, loading, error,
    autoWrite, setAutoWrite, send, clearChat,
    analyses, analysesLoading, analysisFilter, setAnalysisFilter, filteredAnalyses,
    pickerOpen, setPickerOpen, previewEntry, setPreviewEntry,
    selectedAnalysis, setSelectedAnalysis,
    includeSnapshot, setIncludeSnapshot, includeAgentConfig, setIncludeAgentConfig,
    lastInput,
    systemPrompt, agentContextText, onApplySystemPrompt, onApplyAgentContext,
  }
}
