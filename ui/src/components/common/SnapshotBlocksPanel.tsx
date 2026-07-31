/**
 * SnapshotBlocksPanel — visual tool_blocks / calculation_blocks editor.
 *
 * Extracted from the Snapshot Designer's block-management UI
 * (ProfileConfigEditors.tsx) so the Prompt Workbench's Simulation tab uses
 * the same editing experience (dropdown-add, per-tool dynamic argument
 * fields from the tool's own JSON schema, transform_script per block,
 * fullscreen ScriptEditor with the same AI-Assistant context files as the
 * real Snapshot Designer) instead of a second, hand-rolled JSON-only editor.
 * Deliberately excludes the Snapshot Designer's profile save/load CRUD and
 * History — those are out of scope here, the Workbench has its own
 * "load from snapshot profile" mechanism and doesn't persist back to
 * system.json5.
 */
import { useEffect, useState } from 'react'
import { ChevronRight, Trash2 } from 'lucide-react'
import { api, type CalculationBlock, type JsonSchemaProperty, type ToolInfo } from '@/api/client'
import { ScriptEditor } from './ScriptEditor'

export type SnapshotToolBlockForm = {
  _reactKey: string
  id: string
  tool_name: string
  output_key: string
  enabled: boolean
  arguments: Record<string, string>
  transform_script: string
}

export function defaultOutputKey(toolName: string, index: number): string {
  return `${toolName || 'tool'}_${index + 1}`
}

export function defaultArgumentsForTool(toolName: string): Record<string, string> {
  if (toolName === 'get_candles') return { timeframe: 'M5', count: '20' }
  if (toolName === 'calculate_indicator') return { indicator: 'EMA', period: '20', timeframe: 'H1', history: '3' }
  return {}
}

function stringifyArgValue(value: unknown): string {
  if (value === null || value === undefined) return ''
  if (typeof value === 'string') return value
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  try {
    return JSON.stringify(value)
  } catch {
    return String(value)
  }
}

export function normalizeBlockArguments(value: unknown): Record<string, string> {
  if (!value || Array.isArray(value) || typeof value !== 'object') return {}
  const out: Record<string, string> = {}
  for (const [argName, argValue] of Object.entries(value as Record<string, unknown>)) {
    out[argName] = stringifyArgValue(argValue)
  }
  return out
}

export function normalizeToolBlock(raw: unknown, index: number): SnapshotToolBlockForm | null {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return null
  const row = raw as Record<string, unknown>
  const toolName = typeof row.tool_name === 'string' ? row.tool_name : ''
  return {
    _reactKey: crypto.randomUUID(),
    id: typeof row.id === 'string' && row.id ? row.id : `block_${index + 1}`,
    tool_name: toolName,
    output_key: typeof row.output_key === 'string' && row.output_key ? row.output_key : defaultOutputKey(toolName, index),
    enabled: typeof row.enabled === 'boolean' ? row.enabled : true,
    arguments: normalizeBlockArguments(row.arguments),
    transform_script: typeof row.transform_script === 'string' ? row.transform_script : '',
  }
}

export function serializeToolBlock(block: SnapshotToolBlockForm, index: number): Record<string, unknown> {
  const nextArgs: Record<string, unknown> = {}
  for (const [argName, rawValue] of Object.entries(block.arguments)) {
    if (rawValue === '') continue
    nextArgs[argName] = rawValue
  }
  return {
    id: block.id.trim() || `block_${index + 1}`,
    tool_name: block.tool_name,
    output_key: block.output_key.trim() || defaultOutputKey(block.tool_name, index),
    enabled: block.enabled,
    arguments: nextArgs,
    transform_script: block.transform_script,
  }
}

export function normalizeCalculationBlock(raw: unknown, index: number): CalculationBlock | null {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return null
  const row = raw as Record<string, unknown>
  return {
    id: typeof row.id === 'string' && row.id ? row.id : `calc_${index + 1}`,
    type: 'script',
    enabled: typeof row.enabled === 'boolean' ? row.enabled : true,
    sources: {},
    config: {},
    script: typeof row.script === 'string' ? row.script : '',
  }
}

export function serializeCalculationBlock(block: CalculationBlock): Record<string, unknown> {
  return { id: block.id, type: block.type, enabled: block.enabled, script: block.script ?? '' }
}

const selectCls = 'bg-gray-800 border border-gray-600 rounded px-2 py-1 text-sm text-gray-200'
const inputCls = 'mt-1 w-full bg-gray-800 border border-gray-600 rounded px-2 py-1 text-sm text-gray-200'

// tool_blocks assemble a read-only market_snapshot for an LLM to reason over — no
// agent decision is made here, so a tool with a real side effect (place an order,
// raise an alarm, mutate another agent's prompt/memory, run a sub-agent, ...) has
// no business appearing in this picker: it can't influence anything downstream and,
// if actually executed by the assembly pipeline, would fire for real (the backend
// enforces the same list server-side — see analysis_snapshot.py's
// _execute_tool_blocks — this filter is a convenience, not the actual safety net).
// Two separate lists, config/RunTime/snapshot_tool_blocklists.json5 ("snapshot_designer"
// vs "prompt_workbench") — the real Snapshot Designer and the PWB sandbox have
// different requirements (e.g. chart-annotation tools are meaningless/broken in a
// real Snapshot but legitimately usable in the PWB). Fetched fresh, not baked into
// the bundle, so editing the config file takes effect without a rebuild.
export function filterToolsByBlocklist(tools: ToolInfo[], blocked: Set<string>): ToolInfo[] {
  return tools.filter(t => !blocked.has(t.name)).sort((a, b) => a.name.localeCompare(b.name))
}

export function useSnapshotToolBlocklist(key: 'snapshot_designer' | 'prompt_workbench'): Set<string> {
  const [blocked, setBlocked] = useState<Set<string>>(new Set())
  useEffect(() => {
    let cancelled = false
    void api.getConfigFile('snapshot_tool_blocklists').then(cfg => {
      if (cancelled) return
      const list = cfg[key]
      setBlocked(new Set(Array.isArray(list) ? list.filter((n): n is string => typeof n === 'string') : []))
    }).catch(() => {})
    return () => { cancelled = true }
  }, [key])
  return blocked
}

export function ToolBlocksPanel({
  blocks,
  tools: allTools,
  onAdd,
  onRemove,
  onUpdate,
  onUpdateArgument,
  onTest,
  testResultByKey,
}: {
  blocks: SnapshotToolBlockForm[]
  tools: ToolInfo[]
  onAdd: (toolName: string) => void
  onRemove: (index: number) => void
  onUpdate: (index: number, patch: Partial<SnapshotToolBlockForm>) => void
  onUpdateArgument: (index: number, argName: string, value: string) => void
  onTest?: (index: number) => void
  testResultByKey?: Record<string, { loading?: boolean; text?: string; error?: string }>
}) {
  const blockedTools = useSnapshotToolBlocklist('prompt_workbench')
  const tools = filterToolsByBlocklist(allTools, blockedTools)
  const [toolCandidate, setToolCandidate] = useState(tools[0]?.name ?? '')
  useEffect(() => {
    if (!tools.some(t => t.name === toolCandidate)) setToolCandidate(tools[0]?.name ?? '')
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tools])
  const [expanded, setExpanded] = useState<Set<number>>(new Set())
  const toolsByName = new Map(tools.map(t => [t.name, t]))

  const toggle = (index: number) => setExpanded(prev => {
    const next = new Set(prev)
    if (next.has(index)) next.delete(index); else next.add(index)
    return next
  })

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2">
        <select value={toolCandidate} onChange={e => setToolCandidate(e.target.value)} className={selectCls}>
          {tools.length === 0 && <option value="">-- no tools loaded --</option>}
          {tools.map(t => <option key={t.name} value={t.name}>{t.name}</option>)}
        </select>
        <button
          type="button"
          onClick={() => toolCandidate && onAdd(toolCandidate)}
          disabled={!toolCandidate}
          className="text-xs px-3 py-1.5 rounded bg-emerald-700 hover:bg-emerald-600 text-white disabled:opacity-50"
        >
          Add Tool
        </button>
      </div>

      {blocks.length === 0 ? (
        <div className="rounded border border-dashed border-gray-700 px-3 py-3 text-xs text-white">No tool blocks configured.</div>
      ) : (
        <div className="space-y-2">
          {blocks.map((block, index) => {
            const tool = toolsByName.get(block.tool_name)
            const properties = Object.entries(tool?.input_schema.properties ?? {})
            const isExpanded = expanded.has(index)
            const testResult = testResultByKey?.[block._reactKey]
            return (
              <div key={block._reactKey} className="rounded border border-gray-700 bg-gray-900/40">
                <div className="flex items-center gap-2 px-2 py-2 cursor-pointer select-none hover:bg-gray-800/40" onClick={() => toggle(index)}>
                  <ChevronRight className={`w-3.5 h-3.5 text-gray-500 flex-shrink-0 transition-transform duration-150 ${isExpanded ? 'rotate-90' : ''}`} />
                  <span className="font-mono text-xs text-gray-200 w-20 flex-shrink-0 truncate" title={block.id}>{block.id || '—'}</span>
                  <span className="text-[11px] text-white flex-1 truncate" title={block.tool_name}>{block.tool_name}</span>
                  <label className="inline-flex items-center gap-1 text-xs text-white flex-shrink-0" onClick={e => e.stopPropagation()}>
                    <input type="checkbox" checked={block.enabled} onChange={e => onUpdate(index, { enabled: e.target.checked })} />
                    on
                  </label>
                  {onTest && (
                    <button
                      type="button"
                      onClick={e => { e.stopPropagation(); onTest(index) }}
                      className="flex-shrink-0 text-xs px-2 py-0.5 rounded bg-violet-700 hover:bg-violet-600 text-white"
                    >
                      {testResult?.loading ? '…' : 'Test'}
                    </button>
                  )}
                </div>

                {isExpanded && (
                  <div className="border-t border-gray-700 p-2 space-y-2">
                    <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                      <label className="text-xs text-gray-300">
                        Block id
                        <input value={block.id} onChange={e => onUpdate(index, { id: e.target.value })} className={inputCls} />
                      </label>
                      <label className="text-xs text-gray-300">
                        Tool
                        <select
                          value={block.tool_name}
                          onChange={e => onUpdate(index, {
                            tool_name: e.target.value,
                            output_key: defaultOutputKey(e.target.value, index),
                            arguments: defaultArgumentsForTool(e.target.value),
                          })}
                          className={inputCls}
                        >
                          {tools.map(t => <option key={t.name} value={t.name}>{t.name}</option>)}
                        </select>
                      </label>
                      <label className="text-xs text-gray-300">
                        output_key
                        <input value={block.output_key} onChange={e => onUpdate(index, { output_key: e.target.value })} className={inputCls} />
                      </label>
                    </div>

                    {properties.length === 0 ? (
                      <div className="text-[11px] text-white">This tool has no configurable arguments.</div>
                    ) : (
                      <div className="grid grid-cols-2 gap-2">
                        {properties.map(([argName, prop]: [string, JsonSchemaProperty]) => {
                          const value = block.arguments[argName] ?? ''
                          const inputType = prop.type === 'integer' || prop.type === 'number' ? 'number' : 'text'
                          return (
                            <label key={`${block._reactKey}-${argName}`} className="text-xs text-gray-300">
                              <span className="font-mono text-gray-200">{argName}</span>
                              <span className="ml-1 text-gray-600">({prop.type ?? 'any'})</span>
                              {prop.enum ? (
                                <select value={value} onChange={e => onUpdateArgument(index, argName, e.target.value)} className={inputCls}>
                                  <option value="">-- not set --</option>
                                  {argName === 'timeframe' && (
                                    <>
                                      <option value="SHORT_TF">SHORT_TF</option>
                                      <option value="LONG_TF">LONG_TF</option>
                                    </>
                                  )}
                                  {prop.enum.map(o => <option key={o} value={o}>{o}</option>)}
                                </select>
                              ) : prop.type === 'boolean' ? (
                                <select value={value} onChange={e => onUpdateArgument(index, argName, e.target.value)} className={inputCls}>
                                  <option value="">-- not set --</option>
                                  <option value="true">true</option>
                                  <option value="false">false</option>
                                </select>
                              ) : (
                                <input
                                  type={inputType}
                                  value={value}
                                  onChange={e => onUpdateArgument(index, argName, e.target.value)}
                                  placeholder="tool default"
                                  className={inputCls}
                                />
                              )}
                            </label>
                          )
                        })}
                      </div>
                    )}

                    <div className="space-y-1">
                      <span className="text-xs text-gray-300">transform_script</span>
                      <ScriptEditor
                        value={block.transform_script}
                        onChange={v => onUpdate(index, { transform_script: v })}
                        minHeight={100}
                        snippetScope="snapshot"
                        contextFile="script_snapshot_transform_context.md"
                        contextData={`=== Tool Block ===\ntool_name: ${block.tool_name}\noutput_key: ${block.output_key}\narguments:\n${JSON.stringify(block.arguments ?? {}, null, 2)}`}
                      />
                    </div>

                    {testResult && (
                      <pre className="whitespace-pre-wrap break-words text-[11px] text-gray-300 leading-5 bg-gray-950/60 border border-gray-800 rounded p-2">
                        {testResult.error ? `Error: ${testResult.error}` : testResult.text}
                      </pre>
                    )}

                    <div className="flex justify-end">
                      <button type="button" onClick={() => onRemove(index)} className="text-xs px-2 py-1 rounded bg-red-800 hover:bg-red-700 text-white flex items-center gap-1">
                        <Trash2 className="w-3 h-3" /> Remove
                      </button>
                    </div>
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

export function CalculationBlocksPanel({
  blocks,
  onAdd,
  onRemove,
  onUpdate,
  onTest,
  testResultByKey,
}: {
  blocks: CalculationBlock[]
  onAdd: () => void
  onRemove: (index: number) => void
  onUpdate: (index: number, patch: Partial<CalculationBlock>) => void
  onTest?: (index: number) => void
  testResultByKey?: Record<string, { loading?: boolean; text?: string; error?: string }>
}) {
  const [expanded, setExpanded] = useState<Set<number>>(new Set())
  const toggle = (index: number) => setExpanded(prev => {
    const next = new Set(prev)
    if (next.has(index)) next.delete(index); else next.add(index)
    return next
  })

  return (
    <div className="space-y-2">
      <button type="button" onClick={onAdd} className="text-xs px-3 py-1.5 rounded bg-emerald-700 hover:bg-emerald-600 text-white">
        Add Calculation
      </button>

      {blocks.length === 0 ? (
        <div className="rounded border border-dashed border-gray-700 px-3 py-3 text-xs text-white">No calculation blocks configured.</div>
      ) : (
        <div className="space-y-2">
          {blocks.map((block, index) => {
            const isExpanded = expanded.has(index)
            const key = `${block.id}-${index}`
            const testResult = testResultByKey?.[key]
            return (
              <div key={key} className="rounded border border-gray-700 bg-gray-900/40">
                <div className="flex items-center gap-2 px-2 py-2 cursor-pointer select-none hover:bg-gray-800/40" onClick={() => toggle(index)}>
                  <ChevronRight className={`w-3.5 h-3.5 text-gray-500 flex-shrink-0 transition-transform duration-150 ${isExpanded ? 'rotate-90' : ''}`} />
                  <span className="font-mono text-xs text-gray-200 flex-1 truncate" title={block.id}>{block.id || '—'}</span>
                  <label className="inline-flex items-center gap-1 text-xs text-white flex-shrink-0" onClick={e => e.stopPropagation()}>
                    <input type="checkbox" checked={block.enabled} onChange={e => onUpdate(index, { enabled: e.target.checked })} />
                    on
                  </label>
                  {onTest && (
                    <button type="button" onClick={e => { e.stopPropagation(); onTest(index) }} className="flex-shrink-0 text-xs px-2 py-0.5 rounded bg-violet-700 hover:bg-violet-600 text-white">
                      {testResult?.loading ? '…' : 'Test'}
                    </button>
                  )}
                </div>
                {isExpanded && (
                  <div className="border-t border-gray-700 p-2 space-y-2">
                    <label className="block text-xs text-gray-300">
                      id
                      <input value={block.id} onChange={e => onUpdate(index, { id: e.target.value })} className={`${inputCls} font-mono`} />
                    </label>
                    <div className="space-y-1">
                      <span className="text-xs text-gray-300">script</span>
                      <ScriptEditor
                        value={block.script ?? ''}
                        onChange={v => onUpdate(index, { script: v })}
                        minHeight={120}
                        snippetScope="snapshot"
                        contextFile="script_snapshot_calculation_context.md"
                      />
                    </div>
                    {testResult && (
                      <pre className="whitespace-pre-wrap break-words text-[11px] text-gray-300 leading-5 bg-gray-950/60 border border-gray-800 rounded p-2">
                        {testResult.error ? `Error: ${testResult.error}` : testResult.text}
                      </pre>
                    )}
                    <div className="flex justify-end">
                      <button type="button" onClick={() => onRemove(index)} className="text-xs px-2 py-1 rounded bg-red-800 hover:bg-red-700 text-white flex items-center gap-1">
                        <Trash2 className="w-3 h-3" /> Remove
                      </button>
                    </div>
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
