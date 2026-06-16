import { useEffect, useMemo, useState } from 'react'
import JSON5 from 'json5'
import { BookOpen, Bot, Check, ChevronRight, Copy, Play, RefreshCw, Save, Trash2, X } from 'lucide-react'
import { api, type AgentInfo, type CalculationBlock, type CalculationBlockType, type DecisionPromptScriptTestResponse, type JsonSchemaProperty, type SnippetLibraryEntry, type SnapshotCalculationPreviewResponse, type SnapshotPreviewResponse, type SnapshotToolPreviewResponse, type ToolInfo } from '@/api/client'
import { useProjectRoot, joinPath } from '@/api/useProjectRoot'
import { ScriptEditor } from '@/components/common/ScriptEditor'
import { PromptLibraryModal } from '@/components/common/PromptLibraryModal'
import { LLMChatPanel } from '@/components/common/LLMChatPanel'

function CopyButton({ getText }: { getText: () => string }) {
  const [copied, setCopied] = useState(false)
  return (
    <button
      type="button"
      title="Copy to clipboard"
      onClick={() => {
        void navigator.clipboard.writeText(getText()).then(() => {
          setCopied(true)
          setTimeout(() => setCopied(false), 1500)
        })
      }}
      className="inline-flex items-center text-gray-500 hover:text-gray-300 transition-colors"
    >
      {copied ? <Check className="w-3 h-3 text-emerald-400" /> : <Copy className="w-3 h-3" />}
    </button>
  )
}


type SystemConfig = Record<string, unknown> & {
  snapshot_profiles?: Record<string, Record<string, unknown>>
  decision_prompt_profiles?: Record<string, Record<string, unknown>>
}

type SnapshotToolBlockForm = {
  id: string
  tool_name: string
  output_key: string
  enabled: boolean
  arguments: Record<string, string>
  transform_script: string
}

const VALID_TIMEFRAMES = ['M5', 'M15', 'M30', 'H1', 'H4', 'D1'] as const

type SnapshotProfileForm = {
  name: string
  description: string
  short_timeframe: string
  long_timeframe: string
  decision_input_prefix: string
  strategy_aggressiveness: 'CONSERVATIVE' | 'BALANCED' | 'AGGRESSIVE'
  tool_blocks: SnapshotToolBlockForm[]
  calculation_blocks: CalculationBlock[]
  assembly_transform_script: string
}

type DecisionPromptEntry = {
  id: number
  description: string
  mode: 'replace' | 'append'
  prompt: string
  use_placeholders: boolean
}

type DecisionPromptForm = {
  name: string
  description: string
  fallback_snapshot_profile: string
  script: string
  prompts: DecisionPromptEntry[]
}


const DEFAULT_IDENTITY_TRANSFORM_SCRIPT = 'result = tool_output'
const DEFAULT_CANDLE_TRANSFORM_SCRIPT = 'result = normalize_candle_tool_output(tool_output, timeframe=tool_input.get("timeframe"))'
const DEFAULT_INDICATOR_TRANSFORM_SCRIPT = `result = dict(tool_output)
points = tool_output.get("values") or tool_output.get("value") or []
values = []
for item in points:
    if isinstance(item, dict):
        raw_value = item.get("value")
  else:
    raw_value = item
  if raw_value is not None:
    values.append(float(raw_value))
indicator_name = str(tool_output.get("indicator") or tool_input.get("indicator") or "").upper()
result["indicator"] = indicator_name or result.get("indicator")
result["latest"] = latest_value(values)
result["direction"] = classify_indicator_direction(values, indicator_name)
result["values"] = points
if "value" in result:
    del result["value"]`
const EMPTY_SNAPSHOT: SnapshotProfileForm = {
  name: '',
  description: '',
  short_timeframe: 'M5',
  long_timeframe: 'H1',
  decision_input_prefix: 'Runtime-prepared market decision snapshot.\nUse the snapshot as the complete market context.\nReturn strict JSON only.',
  strategy_aggressiveness: 'BALANCED',
  tool_blocks: [
    { id: 'm5_recent',   tool_name: 'get_candles',         output_key: 'm5_recent',   enabled: true, arguments: { timeframe: 'M5',  count: '20'  }, transform_script: DEFAULT_CANDLE_TRANSFORM_SCRIPT },
    { id: 'h1_recent',   tool_name: 'get_candles',         output_key: 'h1_recent',   enabled: true, arguments: { timeframe: 'H1',  count: '120' }, transform_script: DEFAULT_CANDLE_TRANSFORM_SCRIPT },
    { id: 'ema_fast',    tool_name: 'calculate_indicator', output_key: 'ema_fast',    enabled: true, arguments: { indicator: 'EMA', period: '20', timeframe: 'H1', history: '3' }, transform_script: DEFAULT_INDICATOR_TRANSFORM_SCRIPT },
    { id: 'ema_slow',    tool_name: 'calculate_indicator', output_key: 'ema_slow',    enabled: true, arguments: { indicator: 'EMA', period: '50', timeframe: 'H1', history: '3' }, transform_script: DEFAULT_INDICATOR_TRANSFORM_SCRIPT },
    { id: 'rsi_primary', tool_name: 'calculate_indicator', output_key: 'rsi_primary', enabled: true, arguments: { indicator: 'RSI', period: '7',  timeframe: 'H1', history: '3' }, transform_script: DEFAULT_INDICATOR_TRANSFORM_SCRIPT },
    { id: 'atr_primary', tool_name: 'calculate_indicator', output_key: 'atr_primary', enabled: true, arguments: { indicator: 'ATR', period: '7',  timeframe: 'H1', history: '3' }, transform_script: DEFAULT_INDICATOR_TRANSFORM_SCRIPT },
  ],
  calculation_blocks: [],
  assembly_transform_script: '',
}

function createSnapshotForm(options?: { includeDefaultToolBlocks?: boolean; blank?: boolean }): SnapshotProfileForm {
  const includeDefaultToolBlocks = options?.includeDefaultToolBlocks ?? true
  const blank = options?.blank ?? false
  return {
    ...EMPTY_SNAPSHOT,
    description: blank ? '' : EMPTY_SNAPSHOT.description,
    decision_input_prefix: EMPTY_SNAPSHOT.decision_input_prefix,
    strategy_aggressiveness: 'BALANCED',
    tool_blocks: includeDefaultToolBlocks
      ? EMPTY_SNAPSHOT.tool_blocks.map(block => ({ ...block, arguments: { ...block.arguments } }))
      : [],
    calculation_blocks: [],
    assembly_transform_script: blank ? '' : EMPTY_SNAPSHOT.assembly_transform_script,
  }
}

const EMPTY_DECISION: DecisionPromptForm = {
  name: '',
  description: '',
  fallback_snapshot_profile: '',
  script: 'result = 1',
  prompts: [],
}

function toText(v: unknown): string {
  return typeof v === 'string' ? v : ''
}

function toNum(v: unknown, fallback: number): number {
  if (typeof v === 'number' && Number.isFinite(v)) return v
  if (typeof v === 'string') {
    const parsed = Number(v)
    if (Number.isFinite(parsed)) return parsed
  }
  return fallback
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

function normalizeBlockArguments(value: unknown): Record<string, string> {
  if (!value || Array.isArray(value) || typeof value !== 'object') return {}
  const out: Record<string, string> = {}
  for (const [argName, argValue] of Object.entries(value as Record<string, unknown>)) {
    out[argName] = stringifyArgValue(argValue)
  }
  return out
}

function coerceToolArgValue(raw: string, prop?: JsonSchemaProperty): unknown {
  if (raw === '') return undefined
  const type = prop?.type
  if (type === 'integer') {
    const value = Number.parseInt(raw, 10)
    if (!Number.isFinite(value)) throw new Error(`Invalid integer value: ${raw}`)
    return value
  }
  if (type === 'number') {
    const value = Number.parseFloat(raw)
    if (!Number.isFinite(value)) throw new Error(`Invalid number value: ${raw}`)
    return value
  }
  if (type === 'boolean') {
    if (raw === 'true') return true
    if (raw === 'false') return false
    throw new Error(`Invalid boolean value: ${raw}`)
  }
  if (type === 'object' || type === 'array') {
    return JSON5.parse(raw)
  }
  return raw
}

function defaultOutputKey(toolName: string, index: number): string {
  return `${toolName || 'tool'}_${index + 1}`
}

function defaultArgumentsForTool(toolName: string): Record<string, string> {
  if (toolName === 'get_candles') return { timeframe: 'M5', count: '20' }
  if (toolName === 'calculate_indicator') return { indicator: 'EMA', period: '20', timeframe: 'H1', history: '3' }
  return {}
}

function defaultTransformScriptForTool(toolName: string): string {
  if (toolName === 'get_candles') return DEFAULT_CANDLE_TRANSFORM_SCRIPT
  if (toolName === 'calculate_indicator') return DEFAULT_INDICATOR_TRANSFORM_SCRIPT
  return DEFAULT_IDENTITY_TRANSFORM_SCRIPT
}

function buildLegacySnapshotToolBlocks(raw: Record<string, unknown>): SnapshotToolBlockForm[] {
  const candleRequests = raw.candle_requests && typeof raw.candle_requests === 'object'
    ? raw.candle_requests as Record<string, unknown>
    : {}
  const m5Count = Math.max(1, Math.trunc(toNum(candleRequests.m5_count, 20)))
  const h1Count = Math.max(1, Math.trunc(toNum(candleRequests.h1_count, 120)))
  return [
    { id: 'm5_recent', tool_name: 'get_candles', output_key: 'm5_recent', enabled: true, arguments: { timeframe: 'M5', count: String(m5Count) }, transform_script: DEFAULT_CANDLE_TRANSFORM_SCRIPT },
    { id: 'h1_recent', tool_name: 'get_candles', output_key: 'h1_recent', enabled: true, arguments: { timeframe: 'H1', count: String(h1Count) }, transform_script: DEFAULT_CANDLE_TRANSFORM_SCRIPT },
    { id: 'ema_fast', tool_name: 'calculate_indicator', output_key: 'ema_fast', enabled: true, arguments: { indicator: 'EMA', period: '20', timeframe: 'H1', history: '3' }, transform_script: DEFAULT_INDICATOR_TRANSFORM_SCRIPT },
    { id: 'ema_slow', tool_name: 'calculate_indicator', output_key: 'ema_slow', enabled: true, arguments: { indicator: 'EMA', period: '50', timeframe: 'H1', history: '3' }, transform_script: DEFAULT_INDICATOR_TRANSFORM_SCRIPT },
    { id: 'rsi_primary', tool_name: 'calculate_indicator', output_key: 'rsi_primary', enabled: true, arguments: { indicator: 'RSI', period: '7', timeframe: 'H1', history: '3' }, transform_script: DEFAULT_INDICATOR_TRANSFORM_SCRIPT },
    { id: 'atr_primary', tool_name: 'calculate_indicator', output_key: 'atr_primary', enabled: true, arguments: { indicator: 'ATR', period: '7', timeframe: 'H1', history: '3' }, transform_script: DEFAULT_INDICATOR_TRANSFORM_SCRIPT },
  ]
}

function normalizeSnapshotToolBlock(raw: unknown, index: number): SnapshotToolBlockForm | null {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return null
  const row = raw as Record<string, unknown>
  const toolName = toText(row.tool_name)
  return {
    id: toText(row.id) || `block_${index + 1}`,
    tool_name: toolName,
    output_key: toText(row.output_key) || defaultOutputKey(toolName, index),
    enabled: typeof row.enabled === 'boolean' ? row.enabled : true,
    arguments: normalizeBlockArguments(row.arguments),
    transform_script: toText(row.transform_script) || defaultTransformScriptForTool(toolName),
  }
}

function normalizeSnapshotProfile(name: string, raw: unknown): SnapshotProfileForm {
  const row = raw && typeof raw === 'object' ? raw as Record<string, unknown> : {}
  const toolBlocks = Array.isArray(row.tool_blocks)
    ? row.tool_blocks.map((block, index) => normalizeSnapshotToolBlock(block, index)).filter(Boolean) as SnapshotToolBlockForm[]
    : buildLegacySnapshotToolBlocks(row)

  const normalizeTf = (value: unknown, fallback: string): string => {
    const upper = String(value ?? '').toUpperCase()
    return (VALID_TIMEFRAMES as readonly string[]).includes(upper) ? upper : fallback
  }

  return {
    name,
    description: toText(row.description),
    short_timeframe: normalizeTf(row.short_timeframe, 'M5'),
    long_timeframe: normalizeTf(row.long_timeframe, 'H1'),
    decision_input_prefix: toText(row.decision_input_prefix) || EMPTY_SNAPSHOT.decision_input_prefix,
    strategy_aggressiveness: (toText(row.strategy_aggressiveness).toUpperCase() as SnapshotProfileForm['strategy_aggressiveness']) || 'BALANCED',
    tool_blocks: toolBlocks.length > 0 ? toolBlocks : buildLegacySnapshotToolBlocks({}),
    calculation_blocks: Array.isArray(row.calculation_blocks)
      ? (row.calculation_blocks as unknown[])
          .filter((b): b is Record<string, unknown> => !!b && typeof b === 'object' && !Array.isArray(b))
          .map(b => ({
            id: toText(b.id),
            type: 'script' as CalculationBlockType,
            enabled: typeof b.enabled === 'boolean' ? b.enabled : true,
            sources: {},
            config: {},
            script: toText(b.script),
          }))
      : [],
    assembly_transform_script: toText(row.assembly_transform_script),
  }
}

function serializeSnapshotProfile(form: SnapshotProfileForm): Record<string, unknown> {
  return {
    description: form.description.trim(),
    short_timeframe: form.short_timeframe,
    long_timeframe: form.long_timeframe,
    decision_input_prefix: form.decision_input_prefix,
    strategy_aggressiveness: form.strategy_aggressiveness,
    tool_blocks: form.tool_blocks.map((block, index) => {
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
    }),
    ...(form.calculation_blocks.length > 0 ? {
      calculation_blocks: form.calculation_blocks.map(b =>
        b.type === 'script'
          ? { id: b.id, type: b.type, enabled: b.enabled, script: (b as {script?: string}).script ?? '' }
          : { id: b.id, type: b.type, enabled: b.enabled, sources: b.sources, config: b.config }
      ),
    } : {}),
    assembly_transform_script: form.assembly_transform_script,
  }
}

function normalizeDecisionPromptProfile(name: string, raw: unknown): DecisionPromptForm {
  const row = raw && typeof raw === 'object' ? raw as Record<string, unknown> : {}
  const rawPrompts = Array.isArray(row.prompts) ? row.prompts : []
  const prompts: DecisionPromptEntry[] = rawPrompts
    .filter((p): p is Record<string, unknown> => p && typeof p === 'object')
    .map((p): DecisionPromptEntry => {
      const mode = toText(p.mode).toLowerCase()
      return {
        id: typeof p.id === 'number' ? p.id : Number(p.id) || 1,
        description: toText(p.description),
        mode: mode === 'append' ? 'append' : 'replace',
        prompt: toText(p.prompt),
        use_placeholders: Boolean(p.use_placeholders ?? false),
      }
    })
    .sort((a, b) => a.id - b.id)
  return {
    name,
    description: toText(row.description),
    fallback_snapshot_profile: toText(row.fallback_snapshot_profile),
    script: toText(row.script) || 'result = 1',
    prompts,
  }
}

function serializeDecisionPromptProfile(form: DecisionPromptForm): Record<string, unknown> {
  return {
    description: form.description.trim(),
    ...(form.fallback_snapshot_profile.trim() ? { fallback_snapshot_profile: form.fallback_snapshot_profile.trim() } : {}),
    script: form.script,
    prompts: form.prompts.map(p => ({
      id: p.id,
      description: p.description,
      mode: p.mode,
      prompt: p.prompt,
      use_placeholders: p.use_placeholders,
    })),
  }
}

function validateSnapshotProfile(
  form: SnapshotProfileForm,
  allNames: string[],
  selectedName: string | null,
  toolsByName: Map<string, ToolInfo>,
): string[] {
  const issues: string[] = []
  const trimmed = form.name.trim()
  if (!trimmed) issues.push('`name` is required.')
  if (trimmed && allNames.includes(trimmed) && trimmed !== selectedName) {
    issues.push(`Duplicate profile name "${trimmed}".`)
  }
  if (!form.description.trim()) issues.push('`description` is required.')
  if (!form.decision_input_prefix.trim()) issues.push('`decision_input_prefix` is required.')
  if (form.tool_blocks.length === 0) issues.push('Add at least one snapshot tool block.')

  const ids = new Set<string>()
  form.tool_blocks.forEach((block, index) => {
    const blockId = block.id.trim()
    if (!blockId) issues.push(`tool_blocks[${index}].id is required.`)
    if (blockId) {
      if (ids.has(blockId)) issues.push(`Duplicate tool block id "${blockId}".`)
      ids.add(blockId)
    }
    if (!block.tool_name) issues.push(`tool_blocks[${index}].tool_name is required.`)
    const tool = toolsByName.get(block.tool_name)
    if (!tool) {
      issues.push(`Unknown tool "${block.tool_name}" in tool block "${blockId || index + 1}".`)
      return
    }
    const properties = tool.input_schema.properties ?? {}
    for (const [argName, rawValue] of Object.entries(block.arguments)) {
      if (rawValue === '') continue
      const prop = properties[argName]
      if (!prop) {
        issues.push(`Unknown argument "${block.tool_name}.${argName}" in block "${blockId || index + 1}".`)
        continue
      }
      try {
        coerceToolArgValue(rawValue, prop)
      } catch (err) {
        issues.push(`Invalid argument "${block.tool_name}.${argName}" in block "${blockId || index + 1}": ${String(err)}`)
      }
    }
  })
  return issues
}

function validateDecisionPromptProfile(
  form: DecisionPromptForm,
  allNames: string[],
  selectedName: string | null,
): string[] {
  const issues: string[] = []
  const trimmed = form.name.trim()
  if (!trimmed) issues.push('`name` is required.')
  if (trimmed && allNames.includes(trimmed) && trimmed !== selectedName) {
    issues.push(`Duplicate profile name "${trimmed}".`)
  }
  if (!form.description.trim()) issues.push('`description` is required.')
  const ids = form.prompts.map(p => p.id)
  const uniqueIds = new Set(ids)
  if (ids.length !== uniqueIds.size) issues.push('Prompt IDs must be unique.')
  return issues
}

export function SnapshotConfigEditor() {
  const root = useProjectRoot()
  const [cfg, setCfg] = useState<SystemConfig | null>(null)
  const [selectedName, setSelectedName] = useState<string | null>(null)
  const [form, setForm] = useState<SnapshotProfileForm>(createSnapshotForm({ includeDefaultToolBlocks: false, blank: true }))
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [previewOpen, setPreviewOpen] = useState(false)
  const [previewAgentId, setPreviewAgentId] = useState('')
  const [previewAgents, setPreviewAgents] = useState<string[]>([])
  const [previewLoading, setPreviewLoading] = useState(false)
  const [previewError, setPreviewError] = useState<string | null>(null)
  const [previewData, setPreviewData] = useState<SnapshotPreviewResponse | null>(null)
  const [toolPreviewOpen, setToolPreviewOpen] = useState(false)
  const [toolPreviewLoading, setToolPreviewLoading] = useState(false)
  const [toolPreviewError, setToolPreviewError] = useState<string | null>(null)
  const [toolPreviewBlockIndex, setToolPreviewBlockIndex] = useState<number | null>(null)
  const [toolPreviewData, setToolPreviewData] = useState<SnapshotToolPreviewResponse | null>(null)
  const [tools, setTools] = useState<ToolInfo[]>([])
  const [toolCandidate, setToolCandidate] = useState('')
  const [expandedBlocks, setExpandedBlocks] = useState<Set<number>>(new Set())
  const [toolBlocksOpen, setToolBlocksOpen] = useState(false)
  const [calculationsOpen, setCalculationsOpen] = useState(false)
  const [expandedCalcBlocks, setExpandedCalcBlocks] = useState<Set<number>>(new Set())
  const [calcCandidate, setCalcCandidate] = useState<string>('script')
  const [snippetsForCalc, setSnippetsForCalc] = useState<SnippetLibraryEntry[]>([])
  const [calcPreviewBlockIndex, setCalcPreviewBlockIndex] = useState<number | null>(null)
  const [calcPreviewLoading, setCalcPreviewLoading] = useState(false)
  const [calcPreviewError, setCalcPreviewError] = useState<string | null>(null)
  const [calcPreviewData, setCalcPreviewData] = useState<SnapshotCalculationPreviewResponse | null>(null)

  const profileMap = useMemo(
    () => (cfg?.snapshot_profiles ?? {}) as Record<string, Record<string, unknown>>,
    [cfg],
  )
  const names = useMemo(() => Object.keys(profileMap).sort(), [profileMap])
  const toolsByName = useMemo(() => new Map(tools.map(tool => [tool.name, tool])), [tools])
  const issues = useMemo(
    () => validateSnapshotProfile(form, names, selectedName, toolsByName),
    [form, names, selectedName, toolsByName],
  )

  const load = async () => {
    setLoading(true)
    setError(null)
    setMessage(null)
    try {
      const [next, agents, toolResp, snippetLib] = await Promise.all([
        api.getSystemConfig() as Promise<SystemConfig>,
        api.getAgents(),
        api.getTools(),
        api.getSnippetLibrary('snapshot').catch(() => ({ snippets: [] })),
      ])
      const calcSnippets = (snippetLib.snippets ?? []).filter(s =>
        (s.tags ?? '').split(',').map(t => t.trim()).includes('SnapshotCalc')
      )
      setSnippetsForCalc(calcSnippets)
      const nextProfiles = (next.snapshot_profiles ?? {}) as Record<string, Record<string, unknown>>
      const nextNames = Object.keys(nextProfiles).sort()
      const availableAgents = agents
        .map(agent => agent.agent_id)
        .sort()
      setCfg(next)
      setTools(toolResp.tools)
      setToolCandidate(current => current || toolResp.tools[0]?.name || '')
      setPreviewAgents(availableAgents)
      setPreviewAgentId(current => (current && availableAgents.includes(current) ? current : (availableAgents[0] ?? '')))
      if (nextNames.length > 0) {
        setSelectedName(nextNames[0])
        setForm(normalizeSnapshotProfile(nextNames[0], nextProfiles[nextNames[0]]))
      } else {
        setSelectedName(null)
        setForm(createSnapshotForm({ includeDefaultToolBlocks: false, blank: true }))
      }
    } catch (err) {
      setError(String(err))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { void load() }, [])

  useEffect(() => {
    if (!toolCandidate && tools.length > 0) {
      setToolCandidate(tools[0].name)
    }
  }, [toolCandidate, tools])

  useEffect(() => {
    setExpandedBlocks(new Set())
    setExpandedCalcBlocks(new Set())
    setToolBlocksOpen(false)
  }, [selectedName])

  const persist = async (
    nextProfiles: Record<string, Record<string, unknown>>,
    nextSelectedName: string | null,
    okMsg: string,
  ) => {
    if (!cfg) return
    const payload: SystemConfig = { ...cfg, snapshot_profiles: nextProfiles }
    setSaving(true)
    setError(null)
    setMessage(null)
    try {
      await api.saveSystemConfig(payload)
      setCfg(payload)
      setSelectedName(nextSelectedName)
      if (nextSelectedName && nextProfiles[nextSelectedName]) {
        setForm(normalizeSnapshotProfile(nextSelectedName, nextProfiles[nextSelectedName]))
      } else {
        setForm(createSnapshotForm({ includeDefaultToolBlocks: false, blank: true }))
      }
      setMessage(okMsg)
    } catch (err) {
      setError(String(err))
    } finally {
      setSaving(false)
    }
  }

  const selectProfile = (name: string) => {
    setSelectedName(name)
    setForm(normalizeSnapshotProfile(name, profileMap[name]))
    setError(null)
    setMessage(null)
  }

  const setField = <K extends keyof SnapshotProfileForm>(key: K, value: SnapshotProfileForm[K]) => {
    setForm(prev => ({ ...prev, [key]: value }))
  }

  const updateToolBlock = (index: number, patch: Partial<SnapshotToolBlockForm>) => {
    setForm(prev => ({
      ...prev,
      tool_blocks: prev.tool_blocks.map((block, current) => current === index ? { ...block, ...patch } : block),
    }))
  }

  const setToolBlockArgument = (index: number, argName: string, value: string) => {
    setForm(prev => ({
      ...prev,
      tool_blocks: prev.tool_blocks.map((block, current) => current === index
        ? { ...block, arguments: { ...block.arguments, [argName]: value } }
        : block),
    }))
  }

  const clearToolBlockArguments = (index: number) => {
    setForm(prev => ({
      ...prev,
      tool_blocks: prev.tool_blocks.map((block, current) => current === index ? { ...block, arguments: {} } : block),
    }))
  }

  const addToolBlock = () => {
    if (!toolCandidate) return
    setForm(prev => {
      const index = prev.tool_blocks.length
      return {
        ...prev,
        tool_blocks: [
          ...prev.tool_blocks,
          {
            id: `block_${index + 1}`,
            tool_name: toolCandidate,
            output_key: defaultOutputKey(toolCandidate, index),
            enabled: true,
            arguments: defaultArgumentsForTool(toolCandidate),
            transform_script: defaultTransformScriptForTool(toolCandidate),
          },
        ],
      }
    })
  }

  const removeToolBlock = (index: number) => {
    setForm(prev => ({
      ...prev,
      tool_blocks: prev.tool_blocks.filter((_block, current) => current !== index),
    }))
  }

  const addCalcBlock = () => {
    setForm(prev => {
      const index = prev.calculation_blocks.length
      const snippet = snippetsForCalc.find(s => s.id === calcCandidate)
      const newBlock: CalculationBlock = {
        id: snippet
          ? `${snippet.name.toLowerCase().replace(/\W+/g, '_')}_${index + 1}`
          : `script_${index + 1}`,
        type: 'script',
        enabled: true,
        sources: {},
        config: {},
        script: snippet?.code ?? '',
      }
      return { ...prev, calculation_blocks: [...prev.calculation_blocks, newBlock] }
    })
  }

  const removeCalcBlock = (index: number) => {
    setForm(prev => ({
      ...prev,
      calculation_blocks: prev.calculation_blocks.filter((_b, i) => i !== index),
    }))
  }

  const executeCalcPreview = async (index: number) => {
    if (!previewAgentId) {
      setCalcPreviewError('Select an agent context first.')
      setCalcPreviewData(null)
      setToolPreviewOpen(true)
      return
    }
    const block = form.calculation_blocks[index]
    if (!block) return
    setCalcPreviewBlockIndex(index)
    setToolPreviewBlockIndex(null)
    setToolPreviewData(null)
    setToolPreviewError(null)
    setToolPreviewOpen(true)
    setCalcPreviewLoading(true)
    setCalcPreviewError(null)
    setCalcPreviewData(null)

    try {
      // First fetch results for each referenced tool block so the calculation has data to work with.
      const toolResultsMap: Record<string, unknown> = {}
      const referencedOutputKeys = new Set(Object.values(block.sources).filter(Boolean))
      const toolBlocksToFetch = block.type === 'script'
        ? form.tool_blocks  // script blocks receive all tool outputs
        : form.tool_blocks.filter(tb => referencedOutputKeys.has(tb.output_key))
      await Promise.all(toolBlocksToFetch.map(async tb => {
        try {
          const resp = await api.previewSnapshotTool({
            agent_id: previewAgentId,
            tool_block: {
              id: tb.id, tool_name: tb.tool_name,
              output_key: tb.output_key, enabled: true,
              arguments: tb.arguments, transform_script: tb.transform_script,
            },
            short_timeframe: form.short_timeframe,
            long_timeframe: form.long_timeframe,
          })
          toolResultsMap[tb.output_key] = resp.transformed_output ?? resp.raw_output
        } catch {
          // Leave missing — the handler will receive an empty source.
        }
      }))

      const response = await api.previewSnapshotCalculation({
        agent_id: previewAgentId,
        calculation_block: block.type === 'script'
          ? { id: block.id, type: block.type, enabled: true, script: (block as {script?: string}).script ?? '' }
          : { id: block.id, type: block.type, enabled: true, sources: block.sources, config: block.config },
        tool_results: toolResultsMap,
        strategy_aggressiveness: form.strategy_aggressiveness,
        short_timeframe: form.short_timeframe,
        long_timeframe: form.long_timeframe,
      })
      setCalcPreviewData(response)
    } catch (err) {
      setCalcPreviewError(String(err))
    } finally {
      setCalcPreviewLoading(false)
    }
  }

  const handleUpdate = async () => {
    if (!selectedName) {
      setError('No profile selected. Use "Save As New" for a new entry.')
      return
    }
    if (issues.length > 0) {
      setError('Please fix validation issues before updating.')
      return
    }
    const nextName = form.name.trim()
    const nextProfiles = { ...profileMap }
    if (nextName !== selectedName) delete nextProfiles[selectedName]
    nextProfiles[nextName] = serializeSnapshotProfile({ ...form, name: nextName })
    await persist(nextProfiles, nextName, 'Snapshot profile updated and saved.')
  }

  const handleSaveAsNew = async () => {
    if (issues.length > 0) {
      setError('Please fix validation issues before saving.')
      return
    }
    const nextName = form.name.trim()
    const nextProfiles = {
      ...profileMap,
      [nextName]: serializeSnapshotProfile({ ...form, name: nextName }),
    }
    await persist(nextProfiles, nextName, 'Snapshot profile created and saved.')
  }

  const handleDelete = async () => {
    if (!selectedName) {
      setError('No profile selected to delete.')
      return
    }
    const nextProfiles = { ...profileMap }
    delete nextProfiles[selectedName]
    const nextNames = Object.keys(nextProfiles).sort()
    await persist(nextProfiles, nextNames[0] ?? null, 'Snapshot profile deleted and saved.')
  }

  const executePreview = async () => {
    if (!previewAgentId) {
      setPreviewError('Select an agent context first.')
      return
    }
    if (issues.length > 0) {
      setPreviewError('Please fix validation issues before executing the snapshot.')
      return
    }
    setPreviewLoading(true)
    setPreviewError(null)
    try {
      const response = await api.previewSnapshot({
        agent_id: previewAgentId,
        profile_name: form.name.trim() || null,
        profile_override: serializeSnapshotProfile({ ...form, name: form.name.trim() }),
      })
      setPreviewData(response)
    } catch (err) {
      setPreviewData(null)
      setPreviewError(String(err))
    } finally {
      setPreviewLoading(false)
    }
  }

  const executeToolPreview = async (index: number) => {
    if (!previewAgentId) {
      setToolPreviewError('Select an agent context first.')
      setToolPreviewData(null)
      setToolPreviewOpen(true)
      return
    }
    const block = form.tool_blocks[index]
    if (!block) return
    setToolPreviewBlockIndex(index)
    setCalcPreviewBlockIndex(null)
    setCalcPreviewData(null)
    setCalcPreviewError(null)
    setToolPreviewOpen(true)
    setToolPreviewLoading(true)
    setToolPreviewError(null)
    setToolPreviewData(null)
    try {
      const response = await api.previewSnapshotTool({
        agent_id: previewAgentId,
        tool_block: {
          id: block.id,
          tool_name: block.tool_name,
          output_key: block.output_key,
          enabled: block.enabled,
          arguments: block.arguments,
          transform_script: block.transform_script,
        },
        short_timeframe: form.short_timeframe,
        long_timeframe: form.long_timeframe,
      })
      setToolPreviewData(response)
    } catch (err) {
      setToolPreviewError(String(err))
    } finally {
      setToolPreviewLoading(false)
    }
  }

  const summary = useMemo(() => {
    const lines = [
      `Name: ${form.name || '(missing)'}`,
      `Aggressiveness: ${form.strategy_aggressiveness}`,
      `Short TF: ${form.short_timeframe} / Long TF: ${form.long_timeframe}`,
      '',
      'Tool Blocks:',
      ...form.tool_blocks.map(block => `- ${block.id} | ${block.tool_name} | ${block.enabled ? 'enabled' : 'disabled'} | transform=${block.transform_script.trim() ? 'scripted' : 'identity'}`),
      '',
      `Calc Blocks: ${form.calculation_blocks.length}`,
      `Assembly Transform: ${form.assembly_transform_script.trim() ? 'scripted' : 'empty'}`,
    ]
    return lines.join('\n')
  }, [form])

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between px-4 py-2 bg-gray-900 border-b border-gray-700 flex-shrink-0">
        <span className="text-sm text-gray-300 font-medium">Snapshot Config</span>
        <div className="flex items-center gap-3">
          <span className="text-xs text-gray-500">{root ? joinPath(root, 'config', 'system.json5') : 'config/system.json5'} (snapshot_profiles)</span>
          <button
            onClick={() => void load()}
            disabled={loading || saving}
            className="flex items-center gap-1 text-xs text-gray-400 hover:text-gray-200 transition-colors disabled:opacity-40"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        </div>
      </div>

      <div className="flex-1 min-h-0 p-4 bg-gray-950 overflow-auto flex flex-col gap-4">
        {loading && <p className="text-sm text-gray-500 animate-pulse">Loading snapshot profiles…</p>}
        {error && <p className="text-sm text-red-400">Error: {error}</p>}
        {message && <p className="text-sm text-emerald-400">{message}</p>}

        {!loading && (
          <>
            <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
              <label className="text-xs text-gray-300">
                Snapshot Profile
                <select
                  value={selectedName ?? ''}
                  onChange={e => {
        const nextName = e.target.value
        if (!nextName) {
          setSelectedName(null)
          setForm(createSnapshotForm({ includeDefaultToolBlocks: false, blank: true }))
          return
        }
        selectProfile(nextName)
                  }}
                  className="mt-1 w-full bg-gray-800 border border-gray-600 rounded px-3 py-2 text-sm text-gray-200"
                >
                  {names.length === 0 && <option value="">-- no profiles loaded --</option>}
                  {names.map(name => (
                    <option key={name} value={name}>{name}</option>
                  ))}
                </select>
              </label>
              <label className="text-xs text-gray-300">
                Execute Context Agent
                <select
                  value={previewAgentId}
                  onChange={e => setPreviewAgentId(e.target.value)}
                  className="mt-1 w-full bg-gray-800 border border-gray-600 rounded px-3 py-2 text-sm text-gray-200"
                >
                  {previewAgents.length === 0 && <option value="">-- no agent available --</option>}
                  {previewAgents.map(agentId => (
                    <option key={agentId} value={agentId}>{agentId}</option>
                  ))}
                </select>
              </label>
            </div>

            <div className="grid grid-cols-1 xl:grid-cols-10 gap-4 min-h-[380px]">
              <section className="xl:col-span-7 border border-gray-700 rounded p-3 bg-gray-900/40 space-y-3">
                <div className="flex items-center justify-between">
                  <h3 className="text-sm text-gray-200 font-medium">Snapshot Profile Editor</h3>
                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => { setSelectedName(null); setForm(createSnapshotForm({ includeDefaultToolBlocks: false, blank: true })); setError(null); setMessage(null) }}
                      className="text-xs px-3 py-1.5 rounded bg-amber-600 hover:bg-amber-500 text-white border border-amber-400/40"
                    >
                      New Empty Profile
                    </button>
                    <button
                      onClick={() => { setPreviewOpen(true); void executePreview() }}
                      className="text-xs px-3 py-1.5 rounded bg-violet-700 hover:bg-violet-600 text-white disabled:opacity-50 flex items-center gap-1"
                    >
                      <Play className="w-3.5 h-3.5" />
                      Execute
                    </button>
                    <button
                      onClick={() => void handleUpdate()}
                      disabled={saving}
                      className="text-xs px-3 py-1.5 rounded bg-emerald-700 hover:bg-emerald-600 text-white disabled:opacity-50 flex items-center gap-1"
                    >
                      <Save className="w-3.5 h-3.5" />
                      Update
                    </button>
                    <button
                      onClick={() => void handleSaveAsNew()}
                      disabled={saving}
                      className="text-xs px-3 py-1.5 rounded bg-blue-700 hover:bg-blue-600 text-white disabled:opacity-50"
                    >
                      Save As New
                    </button>
                    <button
                      onClick={() => void handleDelete()}
                      disabled={saving || !selectedName}
                      className="text-xs px-3 py-1.5 rounded bg-red-700 hover:bg-red-600 text-white disabled:opacity-50 flex items-center gap-1"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                      Delete
                    </button>
                  </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  <label className="text-xs text-gray-300">
                    Name
                    <input
                      value={form.name}
                      onChange={e => setField('name', e.target.value)}
                      className="mt-1 w-full bg-gray-800 border border-gray-600 rounded px-2 py-1 text-sm text-gray-200"
                    />
                  </label>
                  <label className="text-xs text-gray-300">
                    strategy_aggressiveness
                    <select
                      value={form.strategy_aggressiveness}
                      onChange={e => setField('strategy_aggressiveness', e.target.value as SnapshotProfileForm['strategy_aggressiveness'])}
                      className="mt-1 w-full bg-gray-800 border border-gray-600 rounded px-2 py-1 text-sm text-gray-200"
                    >
                      <option value="CONSERVATIVE">CONSERVATIVE</option>
                      <option value="BALANCED">BALANCED</option>
                      <option value="AGGRESSIVE">AGGRESSIVE</option>
                    </select>
                  </label>
                </div>

                <label className="block text-xs text-gray-300">
                  Description
                  <input
                    value={form.description}
                    onChange={e => setField('description', e.target.value)}
                    className="mt-1 w-full bg-gray-800 border border-gray-600 rounded px-2 py-1 text-sm text-gray-200"
                  />
                </label>

                <div className="block text-xs text-gray-300">
                  <span className="flex items-center gap-1.5">
                    decision_input_prefix
                    <CopyButton getText={() => form.decision_input_prefix} />
                  </span>
                  <textarea
                    value={form.decision_input_prefix}
                    onChange={e => setField('decision_input_prefix', e.target.value)}
                    rows={4}
                    className="mt-1 w-full bg-gray-800 border border-gray-600 rounded px-2 py-1 text-sm text-gray-200 font-mono"
                  />
                </div>

                <div className="flex flex-wrap items-end gap-4">
                  <label className="text-xs text-gray-300">
                    Short timeframe
                    <select
                      value={form.short_timeframe}
                      onChange={e => setField('short_timeframe', e.target.value)}
                      className="mt-1 block bg-gray-800 border border-gray-600 rounded px-2 py-1 text-sm text-gray-200 focus:outline-none focus:border-gray-400"
                    >
                      {VALID_TIMEFRAMES.map(tf => <option key={tf} value={tf}>{tf}</option>)}
                    </select>
                  </label>
                  <label className="text-xs text-gray-300">
                    Long timeframe
                    <select
                      value={form.long_timeframe}
                      onChange={e => setField('long_timeframe', e.target.value)}
                      className="mt-1 block bg-gray-800 border border-gray-600 rounded px-2 py-1 text-sm text-gray-200 focus:outline-none focus:border-gray-400"
                    >
                      {VALID_TIMEFRAMES.map(tf => <option key={tf} value={tf}>{tf}</option>)}
                    </select>
                  </label>
                  <p className="text-[11px] text-gray-500 pb-1">
                    The selected timeframes define the basis for candle data, indicator calculations, and all subsequent labels below.
                  </p>
                </div>

                <div className="rounded border border-gray-700 bg-gray-950/40">
                  <div
                    className="flex items-center gap-2 px-3 py-2.5 cursor-pointer select-none hover:bg-gray-800/30"
                    onClick={() => setToolBlocksOpen(o => !o)}
                  >
                    <ChevronRight className={`w-3.5 h-3.5 text-gray-500 flex-shrink-0 transition-transform duration-150 ${toolBlocksOpen ? 'rotate-90' : ''}`} />
                    <div className="flex-1 min-w-0">
                      <h4 className="text-sm text-gray-200 font-medium">
                        Snapshot Tool Blocks
                        {form.tool_blocks.length > 0 && (
                          <span className="ml-1.5 text-[11px] text-gray-500 font-normal">({form.tool_blocks.length})</span>
                        )}
                      </h4>
                      {!toolBlocksOpen && <p className="text-[11px] text-gray-500">These registered runtime tools build the snapshot deterministically, without LLM tool-use.</p>}
                    </div>
                    {toolBlocksOpen && (
                      <div className="flex items-center gap-2 flex-shrink-0" onClick={e => e.stopPropagation()}>
                        <select
                          value={toolCandidate}
                          onChange={e => setToolCandidate(e.target.value)}
                          className="bg-gray-800 border border-gray-600 rounded px-2 py-1 text-sm text-gray-200 min-w-[200px]"
                        >
                          {tools.length === 0 && <option value="">-- no tools loaded --</option>}
                          {tools.map(tool => <option key={tool.name} value={tool.name}>{tool.name}</option>)}
                        </select>
                        <button
                          type="button"
                          onClick={addToolBlock}
                          className="text-xs px-3 py-1.5 rounded bg-emerald-700 hover:bg-emerald-600 text-white disabled:opacity-50"
                          disabled={!toolCandidate}
                        >
                          Add Tool
                        </button>
                      </div>
                    )}
                  </div>

                  {toolBlocksOpen && (
                  <div className="border-t border-gray-700 p-3 space-y-3">
                  {form.tool_blocks.length === 0 ? (
                    <div className="rounded border border-dashed border-gray-700 px-3 py-3 text-sm text-gray-500">
                      No tool blocks configured.
                    </div>
                  ) : (
                    <div className="space-y-2">
                      {form.tool_blocks.map((block, index) => {
                        const tool = toolsByName.get(block.tool_name)
                        const properties = Object.entries(tool?.input_schema.properties ?? {})
                        const isExpanded = expandedBlocks.has(index)
                        const toggleExpand = () => setExpandedBlocks(prev => {
                          const next = new Set(prev)
                          if (next.has(index)) next.delete(index); else next.add(index)
                          return next
                        })
                        return (
                          <div key={`${block.id}-${index}`} className="rounded border border-gray-700 bg-gray-900/40">
                            {/* Collapsed summary row */}
                            <div
                              className="flex items-center gap-2 px-2 py-2 cursor-pointer select-none hover:bg-gray-800/40"
                              onClick={toggleExpand}
                            >
                              <ChevronRight className={`w-3.5 h-3.5 text-gray-500 flex-shrink-0 transition-transform duration-150 ${isExpanded ? 'rotate-90' : ''}`} />
                              <span className="font-mono text-xs text-gray-200 w-28 flex-shrink-0 truncate" title={block.id}>{block.id || '—'}</span>
                              <span className="text-[11px] text-gray-400 w-36 flex-shrink-0 truncate" title={block.tool_name}>{block.tool_name}</span>
                              <span className="text-[11px] text-gray-500 flex-1 truncate" title={block.output_key}>{block.output_key}</span>
                              <label
                                className="inline-flex items-center gap-1.5 text-xs text-gray-400 flex-shrink-0"
                                onClick={e => e.stopPropagation()}
                              >
                                <input
                                  type="checkbox"
                                  checked={block.enabled}
                                  onChange={e => updateToolBlock(index, { enabled: e.target.checked })}
                                />
                                enabled
                              </label>
                              <button
                                type="button"
                                onClick={e => { e.stopPropagation(); void executeToolPreview(index) }}
                                className="flex-shrink-0 text-xs px-2 py-1 rounded bg-violet-700 hover:bg-violet-600 text-white"
                              >
                                Test
                              </button>
                            </div>

                            {/* Expanded body */}
                            {isExpanded && (
                              <div className="border-t border-gray-700 p-3 space-y-3">
                                <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                                  <label className="text-xs text-gray-300">
                                    Block id
                                    <input
                                      value={block.id}
                                      onChange={e => updateToolBlock(index, { id: e.target.value })}
                                      className="mt-1 w-full bg-gray-800 border border-gray-600 rounded px-2 py-1 text-sm text-gray-200"
                                    />
                                  </label>
                                  <label className="text-xs text-gray-300">
                                    Tool
                                    <select
                                      value={block.tool_name}
                                      onChange={e => updateToolBlock(index, {
                                        tool_name: e.target.value,
                                        output_key: defaultOutputKey(e.target.value, index),
                                        arguments: defaultArgumentsForTool(e.target.value),
                                        transform_script: defaultTransformScriptForTool(e.target.value),
                                      })}
                                      className="mt-1 w-full bg-gray-800 border border-gray-600 rounded px-2 py-1 text-sm text-gray-200"
                                    >
                                      {tools.map(toolItem => <option key={toolItem.name} value={toolItem.name}>{toolItem.name}</option>)}
                                    </select>
                                  </label>
                                  <label className="text-xs text-gray-300">
                                    output_key
                                    <input
                                      value={block.output_key}
                                      onChange={e => updateToolBlock(index, { output_key: e.target.value })}
                                      className="mt-1 w-full bg-gray-800 border border-gray-600 rounded px-2 py-1 text-sm text-gray-200"
                                    />
                                  </label>
                                </div>

                                <div className="flex items-center justify-between">
                                  <div className="text-xs text-gray-300">Arguments</div>
                                  <button
                                    type="button"
                                    onClick={() => clearToolBlockArguments(index)}
                                    className="text-xs px-2 py-1 rounded border border-gray-700 text-gray-300 hover:bg-gray-800"
                                  >
                                    Clear
                                  </button>
                                </div>

                                {properties.length === 0 ? (
                                  <div className="text-[11px] text-gray-500">This tool has no configurable arguments.</div>
                                ) : (
                                  <div className="grid gap-2" style={{ gridTemplateColumns: 'repeat(12, minmax(0, 1fr))' }}>
                                    {properties.map(([argName, prop]) => {
                                      const value = block.arguments[argName] ?? ''
                                      const inputType = prop.type === 'integer' || prop.type === 'number' ? 'number' : 'text'
                                      return (
                                        <label key={`${block.id}-${argName}`} className="col-span-4 text-xs text-gray-300 flex h-full flex-col justify-end">
                                          <span className="font-mono text-gray-200">{argName}</span>
                                          <span className="ml-1 text-gray-600">({prop.type ?? 'any'})</span>
                                          {prop.description && <span className="mt-0.5 block text-[11px] text-gray-500">{prop.description}</span>}
                                          {prop.enum ? (
                                            <select
                                              value={value}
                                              onChange={e => setToolBlockArgument(index, argName, e.target.value)}
                                              className="mt-1 w-full bg-gray-800 border border-gray-600 rounded px-2 py-1 text-sm text-gray-200"
                                            >
                                              <option value="">-- not set --</option>
                                              {argName === 'timeframe' && (
                                                <>
                                                  <option value="SHORT_TF" className="italic">SHORT_TF (profile short timeframe)</option>
                                                  <option value="LONG_TF"  className="italic">LONG_TF  (profile long timeframe)</option>
                                                  <option disabled>──────────────</option>
                                                </>
                                              )}
                                              {prop.enum.map(option => <option key={option} value={option}>{option}</option>)}
                                            </select>
                                          ) : prop.type === 'boolean' ? (
                                            <select
                                              value={value}
                                              onChange={e => setToolBlockArgument(index, argName, e.target.value)}
                                              className="mt-1 w-full bg-gray-800 border border-gray-600 rounded px-2 py-1 text-sm text-gray-200"
                                            >
                                              <option value="">-- not set --</option>
                                              <option value="true">true</option>
                                              <option value="false">false</option>
                                            </select>
                                          ) : (
                                            <input
                                              type={inputType}
                                              value={value}
                                              onChange={e => setToolBlockArgument(index, argName, e.target.value)}
                                              placeholder="leave empty = tool default"
                                              className="mt-1 w-full bg-gray-800 border border-gray-600 rounded px-2 py-1 text-sm text-gray-200"
                                            />
                                          )}
                                        </label>
                                      )
                                    })}
                                  </div>
                                )}

                                <div className="space-y-1">
                                  <div className="text-xs text-gray-300">transform_script</div>
                                  <ScriptEditor
                                    value={block.transform_script}
                                    onChange={v => updateToolBlock(index, { transform_script: v })}
                                    minHeight={140}
                                    snippetScope="snapshot"
                                    contextFile="script_snapshot_transform_context.md"
                                  />
                                </div>
                                <div className="flex justify-end pt-1">
                                  <button
                                    type="button"
                                    onClick={() => removeToolBlock(index)}
                                    className="text-xs px-3 py-1.5 rounded bg-red-800 hover:bg-red-700 text-white"
                                  >
                                    Remove Block
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
                  )}
                </div>

                {/* ── Calculations section ─────────────────────────────── */}
                <div className="rounded border border-gray-700 bg-gray-950/40">
                  <div
                    className="flex items-center gap-2 px-3 py-2.5 cursor-pointer select-none hover:bg-gray-800/30"
                    onClick={() => setCalculationsOpen(o => !o)}
                  >
                    <ChevronRight className={`w-3.5 h-3.5 text-gray-500 flex-shrink-0 transition-transform duration-150 ${calculationsOpen ? 'rotate-90' : ''}`} />
                    <div className="flex-1 min-w-0">
                      <h4 className="text-sm text-gray-200 font-medium">
                        Calculations
                        {form.calculation_blocks.length > 0 && (
                          <span className="ml-1.5 text-[11px] text-gray-500 font-normal">({form.calculation_blocks.length})</span>
                        )}
                      </h4>
                      {!calculationsOpen && (
                        <p className="text-[11px] text-gray-500">
                          Optional configurable calculations using tool block outputs as data sources. Results appear in <code className="font-mono">snapshot.calculations</code>.
                        </p>
                      )}
                    </div>
                  </div>
                  {calculationsOpen && (
                    <div className="border-t border-gray-700 p-3 space-y-3">
                      <div className="flex items-center gap-2">
                        <select
                          value={calcCandidate}
                          onChange={e => setCalcCandidate(e.target.value)}
                          className="bg-gray-800 border border-gray-600 rounded px-2 py-1 text-sm text-gray-200"
                        >
                          <option value="script">Script (empty)</option>
                          {snippetsForCalc.map(s => (
                            <option key={s.id} value={s.id}>{s.name} v{s.version}</option>
                          ))}
                        </select>
                        <button
                          type="button"
                          onClick={addCalcBlock}
                          className="text-xs px-3 py-1.5 rounded bg-emerald-700 hover:bg-emerald-600 text-white"
                        >
                          Add Calculation
                        </button>
                      </div>

                      {form.calculation_blocks.length === 0 ? (
                        <div className="rounded border border-dashed border-gray-700 px-3 py-3 text-sm text-gray-500">
                          No calculation blocks configured. Add one above to start.
                        </div>
                      ) : (
                        <div className="space-y-2">
                          {form.calculation_blocks.map((block, index) => {
                            const isExpanded = expandedCalcBlocks.has(index)
                            const toggleExpand = () => setExpandedCalcBlocks(prev => {
                              const next = new Set(prev)
                              if (next.has(index)) next.delete(index); else next.add(index)
                              return next
                            })
                            return (
                              <div key={`calc-${block.id}-${index}`} className="rounded border border-gray-700 bg-gray-900/40">
                                {/* Collapsed row */}
                                <div
                                  className="flex items-center gap-2 px-2 py-2 cursor-pointer select-none hover:bg-gray-800/40"
                                  onClick={toggleExpand}
                                >
                                  <ChevronRight className={`w-3.5 h-3.5 text-gray-500 flex-shrink-0 transition-transform duration-150 ${isExpanded ? 'rotate-90' : ''}`} />
                                  <span className="font-mono text-xs text-gray-200 w-28 flex-shrink-0 truncate" title={block.id}>{block.id || '—'}</span>
                                  <span className="text-[11px] text-gray-400 flex-1 truncate">script</span>
                                  <label
                                    className="inline-flex items-center gap-1.5 text-xs text-gray-400 flex-shrink-0"
                                    onClick={e => e.stopPropagation()}
                                  >
                                    <input
                                      type="checkbox"
                                      checked={block.enabled}
                                      onChange={e => {
                                        const next = [...form.calculation_blocks]
                                        next[index] = { ...block, enabled: e.target.checked }
                                        setForm(prev => ({ ...prev, calculation_blocks: next }))
                                      }}
                                    />
                                    enabled
                                  </label>
                                  <button
                                    type="button"
                                    title="Test this calculation block"
                                    onClick={e => { e.stopPropagation(); void executeCalcPreview(index) }}
                                    className="text-xs px-2 py-1 rounded border border-gray-700 text-gray-300 hover:bg-gray-800 flex-shrink-0"
                                  >
                                    Test
                                  </button>
                                </div>
                                {/* Expanded body */}
                                {isExpanded && (
                                  <div className="border-t border-gray-700 p-3 space-y-3">
                                    {/* ID */}
                                    <label className="block text-xs text-gray-300">
                                      id
                                      <input
                                        type="text"
                                        value={block.id}
                                        onChange={e => {
                                          const next = [...form.calculation_blocks]
                                          next[index] = { ...block, id: e.target.value }
                                          setForm(prev => ({ ...prev, calculation_blocks: next }))
                                        }}
                                        className="mt-1 w-full bg-gray-800 border border-gray-600 rounded px-2 py-1 text-sm text-gray-200 font-mono"
                                      />
                                    </label>

                                    {/* Script editor */}
                                    <div className="space-y-1">
                                      <div className="text-xs text-gray-300">script</div>
                                      <ScriptEditor
                                        value={(block as {script?: string}).script ?? ''}
                                        onChange={v => {
                                          const next = [...form.calculation_blocks]
                                          next[index] = { ...block, script: v } as CalculationBlock
                                          setForm(prev => ({ ...prev, calculation_blocks: next }))
                                        }}
                                        minHeight={180}
                                        snippetScope="snapshot"
                                        contextFile="script_snapshot_calculation_context.md"
                                      />
                                    </div>

                                    {/* Output location info */}
                                    <div className="text-[11px] text-gray-600 bg-gray-950/60 rounded px-2 py-1.5">
                                      Result saved in <code className="font-mono">snapshot.calculations.global.{block.id || 'script'}</code>
                                    </div>

                                    {/* Remove */}
                                    <button
                                      type="button"
                                      onClick={() => removeCalcBlock(index)}
                                      className="text-xs px-3 py-1.5 rounded border border-red-900 text-red-400 hover:bg-red-900/20 flex items-center gap-1.5"
                                    >
                                      <Trash2 className="w-3 h-3" />
                                      Remove Block
                                    </button>
                                  </div>
                                )}
                              </div>
                            )
                          })}
                        </div>
                      )}
                    </div>
                  )}
                </div>

                <div className="rounded border border-gray-700 bg-gray-950/40 p-3 space-y-3">
                  <div>
                    <h4 className="text-sm text-gray-200 font-medium">Assembly Transform</h4>
                    <p className="text-[11px] text-gray-500">
                      Combines transformed tool outputs into the final snapshot shape. Leave empty to use the current compatibility/default builder.
                    </p>
                  </div>
                  <div className="space-y-1">
                    <div className="text-xs text-gray-300">assembly_transform_script</div>
                    <ScriptEditor
                      value={form.assembly_transform_script}
                      onChange={v => setField('assembly_transform_script', v)}
                      minHeight={220}
                      snippetScope="snapshot"
                      contextFile="script_snapshot_assembly_context.md"
                    />
                  </div>
                </div>


              </section>

              <aside className="xl:col-span-3 border border-gray-700 rounded p-3 bg-gray-900/30">
                <h3 className="text-sm text-gray-200 font-medium mb-2">Live Preview</h3>
                <pre className="text-xs whitespace-pre-wrap text-gray-300 leading-5">{summary}</pre>
                <div className="mt-3 pt-3 border-t border-gray-700">
                  <h4 className="text-xs text-gray-200 font-semibold mb-1">Validation</h4>
                  {issues.length === 0 ? (
                    <p className="text-xs text-emerald-400">No validation issues detected.</p>
                  ) : (
                    <ul className="text-xs text-amber-300 space-y-1">
                      {issues.map(issue => <li key={issue}>- {issue}</li>)}
                    </ul>
                  )}
                </div>
              </aside>
            </div>
          </>
        )}
      </div>

      {previewOpen && (
        <div className="fixed inset-0 z-50 bg-black/70 flex items-center justify-center p-6">
          <div className="w-full max-w-6xl max-h-[88vh] bg-gray-950 border border-gray-700 rounded-xl overflow-hidden flex flex-col">
            <div className="px-5 py-4 border-b border-gray-800 flex items-center justify-between">
              <div>
                <h3 className="text-base font-semibold text-gray-100">Snapshot Execute Preview</h3>
                <p className="text-sm text-gray-400">
                  Exact runtime snapshot output for the current unsaved profile state.
                </p>
              </div>
              <button
                onClick={() => setPreviewOpen(false)}
                className="inline-flex items-center gap-1 px-3 py-1 rounded border border-gray-700 bg-gray-900 text-gray-300 hover:text-white text-sm"
              >
                <X className="w-4 h-4" />
                Close
              </button>
            </div>
            <div className="px-5 py-3 border-b border-gray-800 bg-gray-900/40 flex flex-wrap items-end gap-3">
              <div className="min-w-[420px]">
                <div className="text-xs text-gray-300">Resolved Runtime Context</div>
                <div className="mt-1 rounded border border-gray-700 bg-gray-900 px-3 py-2 text-sm text-gray-200 font-mono">
                  {previewAgentId || 'no-agent-selected'}
                </div>
              </div>
              {previewLoading && <span className="text-sm text-gray-400 animate-pulse">Executing…</span>}
              {previewError && <span className="text-sm text-red-400">{previewError}</span>}
            </div>
            <div className="flex-1 overflow-auto p-5 grid grid-cols-1 xl:grid-cols-2 gap-4">
              <section className="rounded border border-gray-800 bg-gray-900/40 p-4 space-y-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-1.5">
                    <h4 className="text-sm font-medium text-gray-200">Snapshot Output</h4>
                    {previewData && <CopyButton getText={() => JSON.stringify(previewData.snapshot, null, 2)} />}
                  </div>
                  {previewData && (
                    <span className="text-xs text-gray-500">
                      {previewData.broker_name} · {previewData.pair}
                    </span>
                  )}
                </div>
                {previewData ? (
                  <pre className="whitespace-pre-wrap break-words text-xs text-gray-300 leading-5">
                    {JSON.stringify(previewData.snapshot, null, 2)}
                  </pre>
                ) : (
                  <p className="text-sm text-gray-500">
                    Run the preview to see the exact snapshot JSON delivered to the decision layer.
                  </p>
                )}
              </section>
              <section className="rounded border border-gray-800 bg-gray-900/40 p-4 space-y-3">
                <div className="flex items-center gap-1.5">
                  <h4 className="text-sm font-medium text-gray-200">Forwarded Decision Input</h4>
                  {previewData && <CopyButton getText={() => previewData.decision_input} />}
                </div>
                {previewData ? (
                  <pre className="whitespace-pre-wrap break-words text-xs text-gray-300 leading-5">
                    {previewData.decision_input}
                  </pre>
                ) : (
                  <p className="text-sm text-gray-500">
                    The runtime-built input for the LLM appears here after execution.
                  </p>
                )}
                <div className="pt-3 border-t border-gray-800">
                  <h5 className="text-xs font-semibold text-gray-200 mb-2">Validation</h5>
                  {previewData?.validation_errors.length ? (
                    <ul className="text-xs text-amber-300 space-y-1">
                      {previewData.validation_errors.map(issue => <li key={issue}>- {issue}</li>)}
                    </ul>
                  ) : (
                    <p className="text-xs text-emerald-400">Snapshot validation passed.</p>
                  )}
                </div>
                {previewData && (
                  <div className="pt-3 border-t border-gray-800">
                    <h5 className="text-xs font-semibold text-gray-200 mb-2">Trigger Payload</h5>
                    <pre className="whitespace-pre-wrap break-words text-xs text-gray-400 leading-5">
                      {JSON.stringify(previewData.trigger_payload, null, 2)}
                    </pre>
                  </div>
                )}
              </section>
            </div>
          </div>
        </div>
      )}

      {toolPreviewOpen && (
        <div className="fixed inset-0 z-50 bg-black/70 flex items-center justify-center p-6">
          <div className="w-full max-w-6xl max-h-[88vh] bg-gray-950 border border-gray-700 rounded-xl overflow-hidden flex flex-col">
            <div className="px-5 py-4 border-b border-gray-800 flex items-center justify-between">
              <div>
                <h3 className="text-base font-semibold text-gray-100">Tool Transform Preview</h3>
                <p className="text-sm text-gray-400">
                  Raw tool output and transformed output for the selected snapshot tool block.
                </p>
              </div>
              <button
                onClick={() => setToolPreviewOpen(false)}
                className="inline-flex items-center gap-1 px-3 py-1 rounded border border-gray-700 bg-gray-900 text-gray-300 hover:text-white text-sm"
              >
                <X className="w-4 h-4" />
                Close
              </button>
            </div>
            <div className="px-5 py-3 border-b border-gray-800 bg-gray-900/40 flex flex-wrap items-end gap-3">
              <div className="min-w-[320px]">
                <div className="text-xs text-gray-300">Runtime Context</div>
                <div className="mt-1 rounded border border-gray-700 bg-gray-900 px-3 py-2 text-sm text-gray-200 font-mono">
                  {previewAgentId || 'no-agent-selected'}
                </div>
              </div>
              {calcPreviewBlockIndex !== null && form.calculation_blocks[calcPreviewBlockIndex] ? (
                <div className="min-w-[320px]">
                  <div className="text-xs text-gray-300">Calculation Block</div>
                  <div className="mt-1 rounded border border-gray-700 bg-gray-900 px-3 py-2 text-sm text-gray-200 font-mono">
                    {form.calculation_blocks[calcPreviewBlockIndex].id} · {form.calculation_blocks[calcPreviewBlockIndex].type}
                  </div>
                </div>
              ) : toolPreviewBlockIndex !== null && form.tool_blocks[toolPreviewBlockIndex] ? (
                <div className="min-w-[320px]">
                  <div className="text-xs text-gray-300">Tool Block</div>
                  <div className="mt-1 rounded border border-gray-700 bg-gray-900 px-3 py-2 text-sm text-gray-200 font-mono">
                    {form.tool_blocks[toolPreviewBlockIndex].id} · {form.tool_blocks[toolPreviewBlockIndex].tool_name}
                  </div>
                </div>
              ) : null}
              {calcPreviewBlockIndex !== null ? (
                <button
                  onClick={() => { void executeCalcPreview(calcPreviewBlockIndex) }}
                  disabled={calcPreviewLoading}
                  className="text-sm px-4 py-2 rounded bg-violet-700 hover:bg-violet-600 text-white disabled:opacity-50 flex items-center gap-2"
                >
                  <Play className="w-4 h-4" />
                  {calcPreviewLoading ? 'Executing…' : 'Run Calculation'}
                </button>
              ) : (
                <button
                  onClick={() => {
                    if (toolPreviewBlockIndex !== null) void executeToolPreview(toolPreviewBlockIndex)
                  }}
                  disabled={toolPreviewLoading || toolPreviewBlockIndex === null}
                  className="text-sm px-4 py-2 rounded bg-violet-700 hover:bg-violet-600 text-white disabled:opacity-50 flex items-center gap-2"
                >
                  <Play className="w-4 h-4" />
                  {toolPreviewLoading ? 'Executing…' : 'Run Tool'}
                </button>
              )}
              {(calcPreviewError ?? toolPreviewError) && (
                <span className="text-sm text-red-400">{calcPreviewError ?? toolPreviewError}</span>
              )}
            </div>
            <div className="flex-1 overflow-auto p-5 grid grid-cols-1 xl:grid-cols-2 gap-4">
              {calcPreviewBlockIndex !== null ? (
                <>
                  <section className="rounded border border-gray-800 bg-gray-900/40 p-4 space-y-3">
                    <h4 className="text-sm font-medium text-gray-200">Sources (snapshot path)</h4>
                    {calcPreviewBlockIndex !== null && form.calculation_blocks[calcPreviewBlockIndex] ? (
                      <pre className="whitespace-pre-wrap break-words text-xs text-gray-300 leading-5">
                        {JSON.stringify(form.calculation_blocks[calcPreviewBlockIndex].sources, null, 2)}
                      </pre>
                    ) : null}
                  </section>
                  <section className="rounded border border-gray-800 bg-gray-900/40 p-4 space-y-3">
                    <h4 className="text-sm font-medium text-gray-200">Calculation Result</h4>
                    {calcPreviewData ? (
                      <pre className="whitespace-pre-wrap break-words text-xs text-gray-300 leading-5">
                        {JSON.stringify(calcPreviewData.result, null, 2)}
                      </pre>
                    ) : (
                      <p className="text-sm text-gray-500">Run the calculation preview to see results.</p>
                    )}
                    <div className="pt-3 border-t border-gray-800">
                      <h5 className="text-xs font-semibold text-gray-200 mb-2">Errors</h5>
                      {calcPreviewData?.errors.length ? (
                        <ul className="text-xs text-amber-300 space-y-1">
                          {calcPreviewData.errors.map(issue => <li key={issue}>- {issue}</li>)}
                        </ul>
                      ) : (
                        <p className="text-xs text-emerald-400">No errors.</p>
                      )}
                    </div>
                  </section>
                </>
              ) : (
                <>
                  <section className="rounded border border-gray-800 bg-gray-900/40 p-4 space-y-3">
                    <h4 className="text-sm font-medium text-gray-200">Raw Tool Output</h4>
                    {toolPreviewData ? (
                      <pre className="whitespace-pre-wrap break-words text-xs text-gray-300 leading-5">
                        {JSON.stringify(toolPreviewData.raw_output, null, 2)}
                      </pre>
                    ) : (
                      <p className="text-sm text-gray-500">Run the tool preview to see the raw tool output.</p>
                    )}
                  </section>
                  <section className="rounded border border-gray-800 bg-gray-900/40 p-4 space-y-3">
                    <h4 className="text-sm font-medium text-gray-200">Transformed Output</h4>
                    {toolPreviewData ? (
                      <pre className="whitespace-pre-wrap break-words text-xs text-gray-300 leading-5">
                        {JSON.stringify(toolPreviewData.transformed_output, null, 2)}
                      </pre>
                    ) : (
                      <p className="text-sm text-gray-500">Run the tool preview to see the transformed output.</p>
                    )}
                    <div className="pt-3 border-t border-gray-800">
                      <h5 className="text-xs font-semibold text-gray-200 mb-2">Arguments Used</h5>
                      <pre className="whitespace-pre-wrap break-words text-xs text-gray-400 leading-5">
                        {JSON.stringify(
                          toolPreviewBlockIndex !== null ? form.tool_blocks[toolPreviewBlockIndex]?.arguments ?? {} : {},
                          null,
                          2,
                        )}
                      </pre>
                    </div>
                    <div className="pt-3 border-t border-gray-800">
                      <h5 className="text-xs font-semibold text-gray-200 mb-2">Errors</h5>
                      {toolPreviewData?.errors.length ? (
                        <ul className="text-xs text-amber-300 space-y-1">
                          {toolPreviewData.errors.map(issue => <li key={issue}>- {issue}</li>)}
                        </ul>
                      ) : (
                        <p className="text-xs text-emerald-400">No transform or tool errors.</p>
                      )}
                    </div>
                  </section>
                </>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function DecisionPromptTestWindow({
  form,
  initialSnapshot,
  onClose,
}: {
  form: DecisionPromptForm
  initialSnapshot: Record<string, unknown> | null
  onClose: () => void
}) {
  const [snapshotText, setSnapshotText] = useState(
    initialSnapshot ? JSON.stringify(initialSnapshot, null, 2) : '{}',
  )
  const [running, setRunning] = useState(false)
  const [result, setResult] = useState<DecisionPromptScriptTestResponse | null>(null)
  const [runError, setRunError] = useState<string | null>(null)

  const handleRun = async () => {
    setRunning(true)
    setRunError(null)
    setResult(null)
    let snapshot: Record<string, unknown> = {}
    try {
      snapshot = JSON.parse(snapshotText) as Record<string, unknown>
    } catch {
      setRunError('Invalid JSON in snapshot input.')
      setRunning(false)
      return
    }
    try {
      const res = await api.testDecisionPromptScript({
        script: form.script,
        snapshot,
        prompts: form.prompts.map(p => ({ id: p.id, description: p.description, mode: p.mode, prompt: p.prompt, use_placeholders: p.use_placeholders })),
      })
      setResult(res)
    } catch (err) {
      setRunError(String(err))
    } finally {
      setRunning(false)
    }
  }

  useEffect(() => { void handleRun() }, [])

  const matched = result?.matched_prompt
  const matchedPromptText = matched ? String(matched.prompt ?? '') : ''

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70">
      <div className="bg-gray-900 border border-gray-700 rounded-lg w-[90vw] max-w-5xl h-[80vh] flex flex-col">
        <div className="flex items-center justify-between px-4 py-2 border-b border-gray-700 flex-shrink-0">
          <span className="text-sm text-gray-200 font-medium">Script Test Window</span>
          <div className="flex items-center gap-2">
            <button
              onClick={() => void handleRun()}
              disabled={running}
              className="flex items-center gap-1 text-xs px-3 py-1.5 rounded bg-emerald-700 hover:bg-emerald-600 text-white disabled:opacity-50"
            >
              <Play className="w-3.5 h-3.5" />
              {running ? 'Running…' : 'Run'}
            </button>
            <button onClick={onClose} className="text-gray-400 hover:text-gray-200">
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>
        <div className="flex-1 min-h-0 grid grid-cols-2 gap-0 divide-x divide-gray-700">
          <div className="flex flex-col p-3 gap-2 overflow-hidden">
            <div className="flex items-center justify-between flex-shrink-0">
              <span className="text-xs text-gray-400 font-medium">Snapshot Input (editable JSON)</span>
              <CopyButton getText={() => snapshotText} />
            </div>
            <textarea
              value={snapshotText}
              onChange={e => setSnapshotText(e.target.value)}
              className="flex-1 bg-gray-800 border border-gray-600 rounded px-2 py-1 text-xs text-gray-200 font-mono resize-none"
              spellCheck={false}
            />
          </div>
          <div className="flex flex-col p-3 gap-3 overflow-auto">
            <div className="flex items-center justify-between">
              <span className="text-xs text-gray-400 font-medium">Script Result</span>
              {result && !result.error && matchedPromptText && (
                <CopyButton getText={() => matchedPromptText} />
              )}
            </div>
            {runError && <p className="text-xs text-red-400">{runError}</p>}
            {result?.error && <p className="text-xs text-red-400">Script error: {result.error}</p>}
            {result && !result.error && (
              <>
                <div className="flex items-center gap-4 font-mono text-xs">
                  <span className="text-gray-500">result =</span>
                  <span className="text-emerald-400 font-semibold">{result.result ?? '(none)'}</span>
                </div>
                <div className="space-y-0.5">
                  <div className="text-xs text-gray-500">placeholders</div>
                  <pre className="text-xs text-cyan-300 font-mono bg-gray-900 rounded px-2 py-1 whitespace-pre-wrap">
                    {Object.keys(result.placeholders ?? {}).length > 0
                      ? JSON.stringify(result.placeholders, null, 2)
                      : '{}'}
                  </pre>
                </div>
                {matched ? (
                  <div className="border border-gray-700 rounded p-2 space-y-1">
                    <div className="text-xs text-gray-300 font-medium">Matched prompt</div>
                    <div className="text-xs text-gray-400">
                      id: <span className="text-gray-200">{String(matched.id)}</span>
                      {' · '}description: <span className="text-gray-200">{String(matched.description || '—')}</span>
                      {' · '}mode: <span className="text-gray-200">{String(matched.mode)}</span>
                    </div>
                    <pre className="text-xs text-gray-300 whitespace-pre-wrap leading-4 mt-1 max-h-64 overflow-auto">
                      {matchedPromptText.length > 400 ? `${matchedPromptText.slice(0, 400)}\n…[truncated]` : matchedPromptText}
                    </pre>
                    {result.resolved_prompt != null && (
                      <div className="mt-2 pt-2 border-t border-gray-700 space-y-1">
                        <div className="flex items-center justify-between">
                          <span className="text-xs text-cyan-400 font-medium">Resolved (placeholders substituted)</span>
                          <CopyButton getText={() => result.resolved_prompt!} />
                        </div>
                        <pre className="text-xs text-emerald-300 whitespace-pre-wrap leading-4 max-h-40 overflow-auto">
                          {result.resolved_prompt.length > 400 ? `${result.resolved_prompt.slice(0, 400)}\n…[truncated]` : result.resolved_prompt}
                        </pre>
                      </div>
                    )}
                  </div>
                ) : (
                  <p className="text-xs text-amber-400">No prompt matched id {result.result}. First prompt will be used as fallback.</p>
                )}
              </>
            )}
            {!result && !runError && (
              <p className="text-xs text-gray-600">Click Run to execute the selector script.</p>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

export function DecisionPromptConfigEditor() {
  const root = useProjectRoot()
  const [cfg, setCfg] = useState<SystemConfig | null>(null)
  const [selectedName, setSelectedName] = useState<string | null>(null)
  const [form, setForm] = useState<DecisionPromptForm>({ ...EMPTY_DECISION })
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)

  // Right panel — snapshot loader
  const [agents, setAgents] = useState<AgentInfo[]>([])
  const [snapshotProfileNames, setSnapshotProfileNames] = useState<string[]>([])
  const [selectedAgentId, setSelectedAgentId] = useState<string>('')
  const [selectedSnapshotProfile, setSelectedSnapshotProfile] = useState<string>('')
  const [snapshotLoading, setSnapshotLoading] = useState(false)
  const [loadedSnapshot, setLoadedSnapshot] = useState<Record<string, unknown> | null>(null)
  const [snapshotStatus, setSnapshotStatus] = useState<string | null>(null)
  const [snapshotError, setSnapshotError] = useState<string | null>(null)

  // Test window
  const [testOpen, setTestOpen] = useState(false)
  const [libraryOpenForIdx, setLibraryOpenForIdx] = useState<number | null>(null)
  const [llmPromptOpenForIdx, setLlmPromptOpenForIdx] = useState<number | null>(null)

  const profileMap = useMemo(
    () => (cfg?.decision_prompt_profiles ?? {}) as Record<string, Record<string, unknown>>,
    [cfg],
  )
  const names = useMemo(() => Object.keys(profileMap).sort(), [profileMap])
  const issues = useMemo(() => validateDecisionPromptProfile(form, names, selectedName), [form, names, selectedName])

  const load = async () => {
    setLoading(true)
    setError(null)
    setMessage(null)
    try {
      const [next, agentList] = await Promise.all([
        api.getSystemConfig() as Promise<SystemConfig>,
        api.getAgents(),
      ])
      const nextProfiles = (next.decision_prompt_profiles ?? {}) as Record<string, Record<string, unknown>>
      const nextNames = Object.keys(nextProfiles).sort()
      const snapNames = Object.keys((next.snapshot_profiles ?? {}) as Record<string, unknown>).sort()
      setCfg(next)
      setAgents(agentList)
      setSnapshotProfileNames(snapNames)
      if (agentList.length > 0 && !selectedAgentId) setSelectedAgentId(agentList[0].agent_id)
      if (nextNames.length > 0) {
        setSelectedName(nextNames[0])
        setForm(normalizeDecisionPromptProfile(nextNames[0], nextProfiles[nextNames[0]]))
      } else {
        setSelectedName(null)
        setForm({ ...EMPTY_DECISION })
      }
    } catch (err) {
      setError(String(err))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { void load() }, [])

  const persist = async (
    nextProfiles: Record<string, Record<string, unknown>>,
    nextSelectedName: string | null,
    okMsg: string,
  ) => {
    if (!cfg) return
    const payload: SystemConfig = { ...cfg, decision_prompt_profiles: nextProfiles }
    setSaving(true)
    setError(null)
    setMessage(null)
    try {
      await api.saveSystemConfig(payload)
      setCfg(payload)
      setSelectedName(nextSelectedName)
      if (nextSelectedName && nextProfiles[nextSelectedName]) {
        setForm(normalizeDecisionPromptProfile(nextSelectedName, nextProfiles[nextSelectedName]))
      } else {
        setForm({ ...EMPTY_DECISION })
      }
      setMessage(okMsg)
    } catch (err) {
      setError(String(err))
    } finally {
      setSaving(false)
    }
  }

  const selectProfile = (name: string) => {
    setSelectedName(name)
    setForm(normalizeDecisionPromptProfile(name, profileMap[name]))
    setError(null)
    setMessage(null)
  }

  const setField = <K extends keyof DecisionPromptForm>(key: K, value: DecisionPromptForm[K]) => {
    setForm(prev => ({ ...prev, [key]: value }))
  }

  const handleUpdate = async () => {
    if (!selectedName) {
      setError('No profile selected. Use "Save As New" for a new entry.')
      return
    }
    if (issues.length > 0) {
      setError('Please fix validation issues before updating.')
      return
    }
    const nextName = form.name.trim()
    const nextProfiles = { ...profileMap }
    if (nextName !== selectedName) delete nextProfiles[selectedName]
    nextProfiles[nextName] = serializeDecisionPromptProfile({ ...form, name: nextName })
    await persist(nextProfiles, nextName, 'Decision prompt profile updated and saved.')
  }

  const handleSaveAsNew = async () => {
    if (issues.length > 0) {
      setError('Please fix validation issues before saving.')
      return
    }
    const nextName = form.name.trim()
    const nextProfiles = {
      ...profileMap,
      [nextName]: serializeDecisionPromptProfile({ ...form, name: nextName }),
    }
    await persist(nextProfiles, nextName, 'Decision prompt profile created and saved.')
  }

  const handleDelete = async () => {
    if (!selectedName) {
      setError('No profile selected to delete.')
      return
    }
    const nextProfiles = { ...profileMap }
    delete nextProfiles[selectedName]
    const nextNames = Object.keys(nextProfiles).sort()
    await persist(nextProfiles, nextNames[0] ?? null, 'Decision prompt profile deleted and saved.')
  }

  const handleLoadSnapshot = async () => {
    if (!selectedAgentId) return
    setSnapshotLoading(true)
    setSnapshotError(null)
    setSnapshotStatus(null)
    try {
      const res = await api.previewSnapshot({
        agent_id: selectedAgentId,
        profile_name: selectedSnapshotProfile || null,
      })
      setLoadedSnapshot((res.snapshot as Record<string, unknown> | null) ?? {})
      const profileLabel = selectedSnapshotProfile ? ` · ${selectedSnapshotProfile}` : ''
      setSnapshotStatus(`Snapshot loaded · ${selectedAgentId}${profileLabel} · ${new Date().toLocaleTimeString()}`)
    } catch (err) {
      setSnapshotError(String(err))
    } finally {
      setSnapshotLoading(false)
    }
  }

  const nextPromptId = form.prompts.length > 0 ? Math.max(...form.prompts.map(p => p.id)) + 1 : 1

  const addPrompt = () => {
    const entry: DecisionPromptEntry = { id: nextPromptId, description: '', mode: 'replace', prompt: '', use_placeholders: false }
    setField('prompts', [...form.prompts, entry])
  }

  const updatePrompt = (idx: number, patch: Partial<DecisionPromptEntry>) => {
    const next = form.prompts.map((p, i) => i === idx ? { ...p, ...patch } : p)
    setField('prompts', next)
  }

  const duplicatePrompt = (idx: number) => {
    const src = form.prompts[idx]
    const copy: DecisionPromptEntry = { ...src, id: nextPromptId }
    const next = [...form.prompts.slice(0, idx + 1), copy, ...form.prompts.slice(idx + 1)]
    setField('prompts', next)
  }

  const deletePrompt = (idx: number) => {
    setField('prompts', form.prompts.filter((_, i) => i !== idx))
  }

  return (
    <div className="flex flex-col h-full">
      {testOpen && (
        <DecisionPromptTestWindow
          form={form}
          initialSnapshot={loadedSnapshot}
          onClose={() => setTestOpen(false)}
        />
      )}
      {libraryOpenForIdx !== null && (() => {
        const idx = libraryOpenForIdx
        return (
          <PromptLibraryModal
            scope="decision"
            onClose={() => setLibraryOpenForIdx(null)}
            onInsert={text => updatePrompt(idx, { prompt: (form.prompts[idx]?.prompt ?? '') + (form.prompts[idx]?.prompt ? '\n\n' : '') + text })}
            onReplace={text => updatePrompt(idx, { prompt: text })}
          />
        )
      })()}

      {llmPromptOpenForIdx !== null && (() => {
        const idx = llmPromptOpenForIdx
        const entry = form.prompts[idx]
        if (!entry) return null
        return (
          <div className="fixed inset-0 z-50 bg-black/80 flex items-center justify-center p-4">
            <div className="w-full max-w-7xl h-[88vh] bg-gray-950 border border-gray-700 rounded-xl flex flex-col overflow-hidden">
              <div className="flex items-center justify-between px-4 py-2 border-b border-gray-800 flex-shrink-0">
                <span className="text-sm text-gray-200 font-medium">
                  AI Assistant — Prompt {entry.id}{entry.description ? ` · ${entry.description}` : ''}
                </span>
                <button
                  onClick={() => setLlmPromptOpenForIdx(null)}
                  className="inline-flex items-center gap-1 px-2 py-1 rounded border border-gray-700 text-gray-400 hover:text-white text-xs"
                >
                  <X className="w-3.5 h-3.5" /> Close
                </button>
              </div>
              <div className="flex flex-1 overflow-hidden gap-0">
                <div className="flex flex-col w-1/2 border-r border-gray-800 p-3">
                  <span className="text-xs text-gray-400 mb-1">Prompt Text</span>
                  <textarea
                    className="flex-1 w-full bg-gray-900 border border-gray-700 rounded px-2 py-2 text-xs text-gray-200 font-mono resize-none"
                    spellCheck={false}
                    value={entry.prompt}
                    onChange={e => updatePrompt(idx, { prompt: e.target.value })}
                  />
                </div>
                <div className="flex-1 overflow-hidden">
                  <LLMChatPanel
                    code={entry.prompt}
                    contextFile="script_decision_prompt_context.md"
                    initialOpen
                  />
                </div>
              </div>
            </div>
          </div>
        )
      })()}
      <div className="flex items-center justify-between px-4 py-2 bg-gray-900 border-b border-gray-700 flex-shrink-0">
        <span className="text-sm text-gray-300 font-medium">Decision Prompt</span>
        <div className="flex items-center gap-3">
          <span className="text-xs text-gray-500">{root ? joinPath(root, 'config', 'system.json5') : 'config/system.json5'} (decision_prompt_profiles)</span>
          <button
            onClick={() => void load()}
            disabled={loading || saving}
            className="flex items-center gap-1 text-xs text-gray-400 hover:text-gray-200 transition-colors disabled:opacity-40"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        </div>
      </div>

      <div className="flex-1 min-h-0 p-4 bg-gray-950 overflow-auto flex flex-col gap-4">
        {loading && <p className="text-sm text-gray-500 animate-pulse">Loading decision prompt profiles…</p>}
        {error && <p className="text-sm text-red-400">Error: {error}</p>}
        {message && <p className="text-sm text-emerald-400">{message}</p>}

        {!loading && (
          <>
            <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
              <label className="text-xs text-gray-300">
                Decision Prompt Profile
                <select
                  value={selectedName ?? ''}
                  onChange={e => {
                    const nextName = e.target.value
                    if (!nextName) {
                      setSelectedName(null)
                      setForm({ ...EMPTY_DECISION })
                      setError(null)
                      setMessage(null)
                      return
                    }
                    selectProfile(nextName)
                  }}
                  className="mt-1 w-full bg-gray-800 border border-gray-600 rounded px-3 py-2 text-sm text-gray-200"
                >
                  {names.length === 0 && <option value="">-- no profiles --</option>}
                  {names.map(name => (
                    <option key={name} value={name}>{name}</option>
                  ))}
                </select>
              </label>
            </div>

            <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
              {/* Left panel — editor */}
              <section className="border border-gray-700 rounded p-3 bg-gray-900/40 space-y-3">
                <div className="flex items-center justify-between">
                  <h3 className="text-sm text-gray-200 font-medium">Decision Prompt Editor</h3>
                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => { setSelectedName(null); setForm({ ...EMPTY_DECISION }); setError(null); setMessage(null) }}
                      className="text-xs px-3 py-1.5 rounded bg-amber-600 hover:bg-amber-500 text-white border border-amber-400/40"
                    >
                      New Empty Profile
                    </button>
                    <button
                      onClick={() => void handleUpdate()}
                      disabled={saving || issues.length > 0}
                      className="text-xs px-3 py-1.5 rounded bg-emerald-700 hover:bg-emerald-600 text-white disabled:opacity-50 flex items-center gap-1"
                    >
                      <Save className="w-3.5 h-3.5" />
                      Update
                    </button>
                    <button
                      onClick={() => void handleSaveAsNew()}
                      disabled={saving || issues.length > 0}
                      className="text-xs px-3 py-1.5 rounded bg-blue-700 hover:bg-blue-600 text-white disabled:opacity-50"
                    >
                      Save As New
                    </button>
                    <button
                      onClick={() => void handleDelete()}
                      disabled={saving || !selectedName}
                      className="text-xs px-3 py-1.5 rounded bg-red-700 hover:bg-red-600 text-white disabled:opacity-50 flex items-center gap-1"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                      Delete
                    </button>
                  </div>
                </div>

                <label className="block text-xs text-gray-300">
                  Name
                  <input
                    value={form.name}
                    onChange={e => setField('name', e.target.value)}
                    className="mt-1 w-full bg-gray-800 border border-gray-600 rounded px-2 py-1 text-sm text-gray-200"
                  />
                </label>

                <label className="block text-xs text-gray-300">
                  Description
                  <input
                    value={form.description}
                    onChange={e => setField('description', e.target.value)}
                    className="mt-1 w-full bg-gray-800 border border-gray-600 rounded px-2 py-1 text-sm text-gray-200"
                  />
                </label>

                <label className="text-xs text-gray-400">
                  Fallback Snapshot Profile
                  <select
                    value={form.fallback_snapshot_profile}
                    onChange={e => setField('fallback_snapshot_profile', e.target.value)}
                    className="mt-1 w-full bg-gray-800 border border-gray-600 rounded px-2 py-1 text-sm text-gray-200"
                  >
                    <option value="">(none)</option>
                    {snapshotProfileNames.map(n => (
                      <option key={n} value={n}>{n}</option>
                    ))}
                  </select>
                  <span className="text-xs text-gray-600 mt-0.5 block">
                    Executed for selector script data when agent has no snapshot profile assigned. Not forwarded to LLM.
                  </span>
                </label>

                {/* Selector Script */}
                <div>
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-xs text-gray-300">
                      Selector Script
                      <span className="text-gray-500 font-normal ml-1">(Create placeholder: <code className="text-gray-400">placeholders["name"] = value</code> · Use in prompt: <code className="text-gray-400">{'{name}'}</code>)</span>
                    </span>
                    <button
                      onClick={() => setTestOpen(true)}
                      className="flex items-center gap-1 text-xs px-2 py-0.5 rounded border border-gray-600 text-gray-300 hover:bg-gray-700"
                    >
                      <Play className="w-3 h-3" />
                      Test
                    </button>
                  </div>
                  <ScriptEditor
                    minHeight={120}
                    value={form.script}
                    onChange={v => setField('script', v)}
                    snippetScope="decision_prompt"
                    contextFile="script_decision_selector_context.md"
                  />
                </div>

                {/* Prompt Box */}
                <div>
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-xs text-gray-300">Prompts</span>
                    <button
                      onClick={addPrompt}
                      className="text-xs px-2 py-0.5 rounded border border-gray-600 text-gray-300 hover:bg-gray-700"
                    >
                      + New Prompt
                    </button>
                  </div>
                  <div className="space-y-3">
                    {form.prompts.map((entry, idx) => (
                      <div key={idx} className="border border-gray-700 rounded p-2 bg-gray-900 space-y-2">
                        <div className="grid grid-cols-4 gap-2">
                          <label className="text-xs text-gray-400">
                            ID
                            <input
                              type="number"
                              value={entry.id}
                              onChange={e => updatePrompt(idx, { id: Number(e.target.value) || 1 })}
                              className="mt-0.5 w-full bg-gray-800 border border-gray-600 rounded px-2 py-0.5 text-xs text-gray-200"
                            />
                          </label>
                          <label className="text-xs text-gray-400 col-span-1">
                            Description
                            <input
                              value={entry.description}
                              onChange={e => updatePrompt(idx, { description: e.target.value })}
                              className="mt-0.5 w-full bg-gray-800 border border-gray-600 rounded px-2 py-0.5 text-xs text-gray-200"
                            />
                          </label>
                          <label className="text-xs text-gray-400">
                            Mode
                            <select
                              value={entry.mode}
                              onChange={e => updatePrompt(idx, { mode: e.target.value as 'replace' | 'append' })}
                              className="mt-0.5 w-full bg-gray-800 border border-gray-600 rounded px-2 py-0.5 text-xs text-gray-200"
                            >
                              <option value="replace">replace</option>
                              <option value="append">append</option>
                            </select>
                          </label>
                          <label className="flex items-center gap-1.5 text-xs text-gray-400 cursor-pointer self-end pb-0.5">
                            <input
                              type="checkbox"
                              checked={entry.use_placeholders}
                              onChange={e => updatePrompt(idx, { use_placeholders: e.target.checked })}
                              className="accent-cyan-500"
                            />
                            Placeholders
                          </label>
                        </div>
                        <div className="relative">
                          <div className="absolute top-1 right-1 z-10 flex items-center gap-1">
                            <button
                              type="button"
                              title="AI Assistant"
                              onClick={() => setLlmPromptOpenForIdx(idx)}
                              className="inline-flex items-center text-gray-500 hover:text-cyan-400 transition-colors"
                            >
                              <Bot className="w-3 h-3" />
                            </button>
                            <button
                              type="button"
                              title="Prompt Library"
                              onClick={() => setLibraryOpenForIdx(idx)}
                              className="inline-flex items-center text-gray-500 hover:text-gray-300 transition-colors"
                            >
                              <BookOpen className="w-3 h-3" />
                            </button>
                            <CopyButton getText={() => entry.prompt} />
                          </div>
                          <textarea
                            rows={8}
                            value={entry.prompt}
                            onChange={e => updatePrompt(idx, { prompt: e.target.value })}
                            className="w-full bg-gray-800 border border-gray-600 rounded px-2 py-1 pr-6 text-xs text-gray-200 font-mono resize-y"
                            spellCheck={false}
                          />
                        </div>
                        <div className="flex items-center gap-2">
                          <button
                            onClick={() => duplicatePrompt(idx)}
                            className="text-xs px-2 py-0.5 rounded border border-gray-600 text-gray-300 hover:bg-gray-700"
                          >
                            Duplicate
                          </button>
                          <button
                            onClick={() => deletePrompt(idx)}
                            className="flex items-center gap-1 text-xs px-2 py-0.5 rounded border border-red-800 text-red-400 hover:bg-red-900/30"
                          >
                            <Trash2 className="w-3 h-3" />
                            Delete
                          </button>
                        </div>
                      </div>
                    ))}
                    {form.prompts.length === 0 && (
                      <p className="text-xs text-gray-600 italic">No prompts yet. Click "+ New Prompt" to add one.</p>
                    )}
                  </div>
                </div>

                {issues.length > 0 && (
                  <ul className="text-xs text-amber-300 space-y-1">
                    {issues.map(issue => <li key={issue}>- {issue}</li>)}
                  </ul>
                )}
              </section>

              {/* Right panel — snapshot loader */}
              <aside className="border border-gray-700 rounded p-3 bg-gray-900/30 space-y-3">
                <h3 className="text-sm text-gray-200 font-medium">Test Snapshot</h3>
                <div className="grid grid-cols-2 gap-2">
                  <label className="text-xs text-gray-400">
                    Agent
                    <select
                      value={selectedAgentId}
                      onChange={e => setSelectedAgentId(e.target.value)}
                      className="mt-0.5 w-full bg-gray-800 border border-gray-600 rounded px-2 py-1 text-xs text-gray-200"
                    >
                      {agents.length === 0 && <option value="">No agents</option>}
                      {agents.map(a => (
                        <option key={a.agent_id} value={a.agent_id}>{a.agent_id}</option>
                      ))}
                    </select>
                  </label>
                  <label className="text-xs text-gray-400">
                    Snapshot Profile
                    <select
                      value={selectedSnapshotProfile}
                      onChange={e => setSelectedSnapshotProfile(e.target.value)}
                      className="mt-0.5 w-full bg-gray-800 border border-gray-600 rounded px-2 py-1 text-xs text-gray-200"
                    >
                      <option value="">(agent default)</option>
                      {snapshotProfileNames.map(n => (
                        <option key={n} value={n}>{n}</option>
                      ))}
                    </select>
                  </label>
                </div>
                <button
                  onClick={() => void handleLoadSnapshot()}
                  disabled={snapshotLoading || !selectedAgentId}
                  className="text-xs px-3 py-1.5 rounded bg-gray-700 hover:bg-gray-600 text-gray-200 disabled:opacity-50 whitespace-nowrap"
                >
                  {snapshotLoading ? 'Loading…' : 'Load Snapshot'}
                </button>
                {snapshotError && <p className="text-xs text-red-400">{snapshotError}</p>}
                {snapshotStatus && <p className="text-xs text-emerald-400">{snapshotStatus}</p>}
                {loadedSnapshot && (
                  <div>
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-xs text-gray-500">Snapshot JSON</span>
                      <CopyButton getText={() => JSON.stringify(loadedSnapshot, null, 2)} />
                    </div>
                    <pre className="text-xs text-gray-400 bg-gray-800 rounded p-2 max-h-64 overflow-auto whitespace-pre-wrap">
                      {JSON.stringify(loadedSnapshot, null, 2).slice(0, 2000)}
                      {JSON.stringify(loadedSnapshot, null, 2).length > 2000 ? '\n…[truncated]' : ''}
                    </pre>
                  </div>
                )}
                {!loadedSnapshot && !snapshotError && (
                  <p className="text-xs text-gray-600 italic">Select an agent and click "Load Snapshot" to load a live snapshot for testing. The loaded snapshot will be pre-filled in the test window.</p>
                )}
              </aside>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
