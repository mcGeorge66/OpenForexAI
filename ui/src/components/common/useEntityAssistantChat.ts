/**
 * useEntityAssistantChat — state/logic for the EventComposer entity assistant.
 * Split out of EntityAssistantPanel.tsx (a Fast Refresh requirement: that file
 * must only export the component).
 *
 * Create ONE instance per entity being edited and pass its return value into
 * as many `<EntityAssistantPanel chat={...} />` renderings as needed (e.g. the
 * EC wizard's own "LLM Assistant" tab AND the fullscreen Script editor's
 * "Assistant" tab) — both stay in sync since they share this one state object
 * instead of each owning a disconnected copy.
 */

import { useRef, useState, type Dispatch, type SetStateAction } from 'react'
import { api, type ECExecuteResponse, type ToolInfo } from '@/api/client'
import {
  applyDiffHunk,
  applyPatch,
  buildParsedResponse,
  type AssistantMessage,
  type ParsedResponse,
} from '@/components/common/assistantShared'

export interface EntityAssistantPanelProps {
  script: string
  configJson: string
  allowedTools: string[]
  // Full schema (description + input_schema) for each tool in allowedTools — lets the
  // assistant know exactly which JSON arguments each assigned tool accepts, instead of
  // just its name, so it can write/verify tools.call(...) invocations correctly.
  toolSchemas?: ToolInfo[]
  testInput: string
  testResult: ECExecuteResponse | null
  contextFile?: string
  // Name of the snapshot_profiles entry this EC is wired to (if any) — tells the assistant
  // whether the `snapshot` global actually exists in this script's namespace.
  snapshotProfile?: string
  // Full entity form (ec_id, comment, broker, pair, enable, event_triggers, session_filter,
  // timer, any_candle, max_tool_turns, script_timeout_seconds, ...) — everything besides the
  // script/config already sent separately above. Lets the assistant answer "why doesn't this
  // EC run" questions that hinge on triggers/session filter/enable, not just script logic.
  entityConfig?: Record<string, unknown>
  onApplyScript: (code: string) => void
  onApplyConfig: (json: string) => void
  onRunTest: () => Promise<ECExecuteResponse | null>
}

export interface EntityAssistantChat {
  history: AssistantMessage[]
  input: string
  setInput: (v: string) => void
  loading: boolean
  error: string | null
  autoWrite: boolean
  setAutoWrite: Dispatch<SetStateAction<boolean>>
  canTest: boolean
  setCanTest: Dispatch<SetStateAction<boolean>>
  send: () => void
  clearChat: () => void
  script: string
  configJson: string
  onApplyScript: (code: string) => void
  onApplyConfig: (json: string) => void
}

const MAX_AUTO_ITERATIONS = 5
const CONTEXT_FILE_DEFAULT = 'entity_config_assistant.md'

export function useEntityAssistantChat({
  script,
  configJson,
  allowedTools,
  toolSchemas,
  testInput,
  testResult,
  contextFile = CONTEXT_FILE_DEFAULT,
  snapshotProfile,
  entityConfig,
  onApplyScript,
  onApplyConfig,
  onRunTest,
}: EntityAssistantPanelProps): EntityAssistantChat {
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [autoWrite, setAutoWrite] = useState(false)
  const [canTest, setCanTest] = useState(false)
  const [history, setHistory] = useState<AssistantMessage[]>([])

  const historyRef = useRef(history)
  historyRef.current = history

  const scriptRef = useRef(script); scriptRef.current = script
  const configJsonRef = useRef(configJson); configJsonRef.current = configJson
  const toolSchemasRef = useRef(toolSchemas); toolSchemasRef.current = toolSchemas
  const testInputRef = useRef(testInput); testInputRef.current = testInput
  const snapshotProfileRef = useRef(snapshotProfile); snapshotProfileRef.current = snapshotProfile
  const entityConfigRef = useRef(entityConfig); entityConfigRef.current = entityConfig
  const autoWriteRef = useRef(autoWrite); autoWriteRef.current = autoWrite
  const canTestRef = useRef(canTest); canTestRef.current = canTest
  const onApplyScriptRef = useRef(onApplyScript); onApplyScriptRef.current = onApplyScript
  const onApplyConfigRef = useRef(onApplyConfig); onApplyConfigRef.current = onApplyConfig
  const onRunTestRef = useRef(onRunTest); onRunTestRef.current = onRunTest

  function buildContextData(lastResult?: ECExecuteResponse | null): string {
    const lines = scriptRef.current.split('\n')
    const numbered = lines.map((l, i) => `${String(i + 1).padStart(4, ' ')} | ${l}`).join('\n')
    const parts = [
      `=== Script (Python, with line numbers) ===\n\`\`\`\n${numbered}\n\`\`\``,
      `=== Config JSON ===\n\`\`\`json\n${configJsonRef.current}\n\`\`\``,
    ]
    const schemas = toolSchemasRef.current
    if (schemas?.length) {
      const toolDocs = schemas.map(t =>
        `- ${t.name}: ${t.description}\n  input_schema: ${JSON.stringify(t.input_schema)}`,
      ).join('\n')
      parts.push(`=== Allowed Tools (full schema — this is exactly what tools.call() accepts) ===\n${toolDocs}`)
    } else {
      parts.push(`=== Allowed Tools ===\n${allowedTools.length ? allowedTools.join(', ') : '(none)'}`)
    }
    parts.push(
      `=== Snapshot Profile ===\n${
        snapshotProfileRef.current
          ? `"${snapshotProfileRef.current}" — the \`snapshot\` global IS available in this script.`
          : '(none) — the `snapshot` global does NOT exist; referencing it raises NameError.'
      }`,
    )
    if (entityConfigRef.current) {
      parts.push(
        `=== Entity Configuration (id, comment, broker, pair, enable, event_triggers, ` +
        `session_filter, timer, any_candle, max_tool_turns, script_timeout_seconds) ===\n` +
        `\`\`\`json\n${JSON.stringify(entityConfigRef.current, null, 2)}\n\`\`\``,
      )
    }
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
      if (seg.type === 'diffhunk') {
        const source = seg.block.target === 'script' ? scriptRef.current : configJsonRef.current
        const { result, error: applyError } = applyDiffHunk(source, seg.block)
        if (!applyError) {
          if (seg.block.target === 'script') onApplyScriptRef.current(result)
          if (seg.block.target === 'config') onApplyConfigRef.current(result)
        }
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
        allow_change_proposals: true,
      })
      if (resp.error) { setError(resp.error); setLoading(false); return }

      const parsed = buildParsedResponse(resp.answer, resp.proposals)
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

  const send = () => {
    const question = input.trim()
    if (!question || loading) return
    appendMessage({ role: 'user', content: question })
    setInput('')
    void runAgentLoop(question)
  }

  const clearChat = () => { setHistory([]); setError(null) }

  return {
    history, input, setInput, loading, error,
    autoWrite, setAutoWrite, canTest, setCanTest,
    send, clearChat,
    script, configJson, onApplyScript, onApplyConfig,
  }
}
