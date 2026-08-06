/**
 * Pure helpers/types/hook for SnapshotBlocksPanel.tsx's tool_blocks/calculation_blocks
 * editor — split into its own file so that component file only exports components
 * (Fast Refresh requirement), while these stay importable independently (used for
 * (de)serializing blocks to/from system.json5 outside the panel UI too).
 */
import { useEffect, useState } from 'react'
import { api, type CalculationBlock, type ToolInfo } from '@/api/client'

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
