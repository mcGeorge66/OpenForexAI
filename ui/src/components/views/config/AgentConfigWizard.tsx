import { useEffect, useMemo, useState } from 'react'
import JSON5 from 'json5'
import { RefreshCw, Save, Trash2, Plus, Minus } from 'lucide-react'
import { api, type ToolInfo } from '@/api/client'

type SystemConfig = Record<string, unknown> & {
  modules?: {
    llm?: Record<string, string>
    broker?: Record<string, string>
  }
  agents?: Record<string, Record<string, unknown>>
}

type AgentForm = {
  agent_id: string
  comment: string
  enable: boolean
  pair: string
  type: string
  llm: string
  broker: string
  timer_enabled: boolean
  timer_interval_seconds: number
  any_candle: number
  system_prompt: string
  event_triggers: string[]
  allowed_tools: string[]
  context_tiers_text: string
  tier_tools_text: string
  max_tool_turns: number
  max_tokens: number
}

type AgentRow = {
  raw: Record<string, unknown>
  form: AgentForm
}

const DEFAULT_EVENT_TRIGGERS = [
  'm5_candle_available',
  'prompt_updated',
  'agent_query',
  'analysis_result',
  'signal_generated',
  'account_status_updated',
  'risk_breach',
  'order_book_sync_discrepancy',
]

const EMPTY_FORM: AgentForm = {
  agent_id: '',
  comment: '',
  enable: true,
  pair: 'EURUSD',
  type: 'AA',
  llm: '',
  broker: '',
  timer_enabled: false,
  timer_interval_seconds: 300,
  any_candle: 1,
  system_prompt: '',
  event_triggers: ['m5_candle_available'],
  allowed_tools: ['get_candles', 'calculate_indicator', 'raise_alarm'],
  context_tiers_text: '{\n  "0": "all",\n  "85": "safety"\n}',
  tier_tools_text: '{\n  "all": ["*"],\n  "safety": ["raise_alarm"]\n}',
  max_tool_turns: 8,
  max_tokens: 4096,
}

const AGENT_ID_RE = /^[A-Z0-9_]{5}-[A-Z0-9_]{6}-[A-Z]{2}-[A-Z0-9]{1,5}(?:-.+)?$/

const TIPS = {
  agent_id: 'Unique agent identifier. Format: BROKER(5)-PAIR(6)-TYPE(2)-NAME(1-5), e.g. OAPR1-EURUSD-AA-ANLYS. This key is used for routing and startup.',
  enable: 'If true, the agent is started and receives events. If false, the config stays stored but agent is inactive.',
  comment: 'Human-readable note for maintainers. No runtime effect.',
  pair: 'Trading pair (6 chars recommended), e.g. EURUSD or ALL___. Required for AA agents.',
  type: 'Agent role code: AA (Analysis), BA (Broker), GA (Global), AD (Adapter/system use). Influences behavior and routing.',
  llm: 'LLM module name from modules.llm in system config. Determines model/provider used by this agent.',
  broker: 'Broker module name from modules.broker in system config. Determines broker adapter context.',
  timer_enabled: 'If true, the agent runs on a periodic timer in addition to event-triggered execution.',
  timer_interval_seconds: 'Timer period in seconds. Used only when Timer Enabled is true.',
  any_candle: 'Runs on every Nth M5 candle event. 1 = every candle (5m), 3 = every third candle (15m). Only affects m5_candle_available trigger.',
  system_prompt: 'Primary instruction prompt for this agent. Strongly affects decision logic and response style.',
  event_triggers: 'Events that trigger this agent cycle. Only listed events will wake this agent from bus traffic.',
  allowed_tools: 'Tool allow-list for this agent. Only listed tools can be called by the LLM.',
  context_tiers: 'JSON object mapping context budget thresholds to tier names, e.g. {"0":"all","85":"safety"}.',
  tier_tools: 'JSON object mapping each tier to allowed tools. Used by ToolDispatcher budget gating.',
  max_tool_turns: 'Maximum tool-calling iterations per cycle. Prevents runaway tool loops.',
  max_tokens: 'Maximum token budget for this agent response/tool cycle.',
} as const

function toText(v: unknown): string {
  return typeof v === 'string' ? v : ''
}

function toNum(v: unknown, fallback: number): number {
  if (typeof v === 'number' && Number.isFinite(v)) return v
  if (typeof v === 'string') {
    const n = Number(v)
    if (Number.isFinite(n)) return n
  }
  return fallback
}

function toBool(v: unknown, fallback: boolean): boolean {
  if (typeof v === 'boolean') return v
  return fallback
}

function toStringList(v: unknown): string[] {
  if (!Array.isArray(v)) return []
  return v.map(x => String(x).trim()).filter(Boolean)
}

function prettyJson(value: unknown, fallback: string): string {
  try {
    return JSON.stringify(value ?? JSON5.parse(fallback), null, 2)
  } catch {
    return fallback
  }
}

function normalizeAgent(raw: Record<string, unknown>, agentId: string): AgentForm {
  const timer = (raw.timer as Record<string, unknown> | undefined) ?? {}
  const toolCfg = (raw.tool_config as Record<string, unknown> | undefined) ?? {}

  return {
    agent_id: agentId,
    comment: toText(raw._comment),
    enable: toBool(raw.enable, true),
    pair: toText(raw.pair) || 'EURUSD',
    type: toText(raw.type) || 'AA',
    llm: toText(raw.llm),
    broker: toText(raw.broker),
    timer_enabled: toBool(timer.enabled, false),
    timer_interval_seconds: toNum(timer.interval_seconds, 300),
    any_candle: Math.max(1, Math.trunc(toNum(raw.AnyCandle ?? raw.any_candle, 1))),
    system_prompt: toText(raw.system_prompt),
    event_triggers: toStringList(raw.event_triggers),
    allowed_tools: toStringList(toolCfg.allowed_tools),
    context_tiers_text: prettyJson(toolCfg.context_tiers, '{}'),
    tier_tools_text: prettyJson(toolCfg.tier_tools, '{}'),
    max_tool_turns: toNum(toolCfg.max_tool_turns, 8),
    max_tokens: toNum(toolCfg.max_tokens, 4096),
  }
}

function parseJsonObject(text: string): Record<string, unknown> {
  const parsed = JSON5.parse(text)
  if (!parsed || Array.isArray(parsed) || typeof parsed !== 'object') {
    throw new Error('Expected a JSON object.')
  }
  return parsed as Record<string, unknown>
}

function serializeAgent(form: AgentForm, raw: Record<string, unknown>): Record<string, unknown> {
  const next = { ...raw }

  next._comment = form.comment.trim()
  next.enable = form.enable
  next.type = form.type.trim().toUpperCase()
  next.llm = form.llm.trim()
  next.broker = form.broker.trim()

  if (form.type.trim().toUpperCase() === 'AA') {
    next.pair = form.pair.trim().toUpperCase()
  } else {
    delete next.pair
  }

  next.timer = {
    enabled: form.timer_enabled,
    interval_seconds: form.timer_interval_seconds,
  }

  next.event_triggers = form.event_triggers
  next.AnyCandle = Math.max(1, Math.trunc(form.any_candle))
  delete next.any_candle
  next.system_prompt = form.system_prompt
  delete next.chat_instruction

  const prevToolCfg = (raw.tool_config as Record<string, unknown> | undefined) ?? {}
  next.tool_config = {
    ...prevToolCfg,
    allowed_tools: form.allowed_tools,
    context_tiers: parseJsonObject(form.context_tiers_text),
    tier_tools: parseJsonObject(form.tier_tools_text),
    max_tool_turns: form.max_tool_turns,
    max_tokens: form.max_tokens,
  }

  return next
}

function validateForm(form: AgentForm, rows: AgentRow[], selectedIndex: number | null): string[] {
  const issues: string[] = []

  const id = form.agent_id.trim().toUpperCase()
  if (!id) issues.push('`agent_id` is required.')
  if (id && !AGENT_ID_RE.test(id)) {
    issues.push('`agent_id` format invalid. Expected BROKER(5)-PAIR(6)-TYPE(2)-NAME(1-5).')
  }

  const duplicate = rows.findIndex((r, idx) => idx !== selectedIndex && r.form.agent_id.trim().toUpperCase() === id)
  if (id && duplicate >= 0) {
    issues.push(`Duplicate agent_id: "${id}" already exists in row ${duplicate + 1}.`)
  }

  if (!form.type.trim()) issues.push('`type` is required.')
  if (!form.llm.trim()) issues.push('`llm` is required.')
  if (!form.broker.trim()) issues.push('`broker` is required.')
  if (form.type.trim().toUpperCase() === 'AA' && !form.pair.trim()) issues.push('`pair` is required for AA agents.')
  if (!Number.isFinite(form.timer_interval_seconds) || form.timer_interval_seconds < 0) {
    issues.push('`timer.interval_seconds` must be >= 0.')
  }
  if (!Number.isFinite(form.any_candle) || form.any_candle < 1) {
    issues.push('`AnyCandle` must be >= 1.')
  }

  if (form.event_triggers.length === 0) issues.push('At least one `event_trigger` is required.')
  if (!form.system_prompt.trim()) issues.push('`system_prompt` is required.')
  if (form.allowed_tools.length === 0) issues.push('At least one `allowed_tool` is required.')

  try {
    parseJsonObject(form.context_tiers_text)
  } catch (err) {
    issues.push(`Invalid tool_config.context_tiers: ${String(err)}`)
  }

  try {
    parseJsonObject(form.tier_tools_text)
  } catch (err) {
    issues.push(`Invalid tool_config.tier_tools: ${String(err)}`)
  }

  if (!Number.isFinite(form.max_tool_turns) || form.max_tool_turns <= 0) {
    issues.push('`tool_config.max_tool_turns` must be > 0.')
  }
  if (!Number.isFinite(form.max_tokens) || form.max_tokens <= 0) {
    issues.push('`tool_config.max_tokens` must be > 0.')
  }

  return issues
}

function uniqueSorted(values: string[]): string[] {
  return Array.from(new Set(values.filter(Boolean))).sort((a, b) => a.localeCompare(b))
}

export function AgentConfigWizard() {
  const [cfg, setCfg] = useState<SystemConfig | null>(null)
  const [rows, setRows] = useState<AgentRow[]>([])
  const [selectedIndex, setSelectedIndex] = useState<number | null>(null)
  const [form, setForm] = useState<AgentForm>({ ...EMPTY_FORM })
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [tools, setTools] = useState<ToolInfo[]>([])
  const [triggerCandidate, setTriggerCandidate] = useState('')
  const [toolCandidate, setToolCandidate] = useState('')

  const llmNames = useMemo(() => Object.keys(cfg?.modules?.llm ?? {}), [cfg])
  const brokerNames = useMemo(() => Object.keys(cfg?.modules?.broker ?? {}), [cfg])

  const allTriggerOptions = useMemo(() => {
    const fromRows = rows.flatMap(r => r.form.event_triggers)
    return uniqueSorted([...DEFAULT_EVENT_TRIGGERS, ...fromRows])
  }, [rows])

  const allToolNames = useMemo(() => uniqueSorted(tools.map(t => t.name)), [tools])

  const load = async () => {
    setLoading(true)
    setError(null)
    setMessage(null)
    try {
      const [sys, toolResp] = await Promise.all([
        api.getSystemConfig(),
        api.getTools(),
      ])
      const system = sys as SystemConfig
      const agentEntries = Object.entries(system.agents ?? {})
      const normalized: AgentRow[] = agentEntries.map(([agentId, raw]) => {
        const agentRaw = (raw as Record<string, unknown>) ?? {}
        return {
          raw: agentRaw,
          form: normalizeAgent(agentRaw, agentId),
        }
      })

      setCfg(system)
      setTools(toolResp.tools)
      setRows(normalized)
      if (normalized.length > 0) {
        setSelectedIndex(0)
        setForm(normalized[0].form)
      } else {
        setSelectedIndex(null)
        setForm({ ...EMPTY_FORM })
      }
    } catch (err) {
      setError(String(err))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void load()
  }, [])

  useEffect(() => {
    if (!triggerCandidate && allTriggerOptions.length > 0) {
      setTriggerCandidate(allTriggerOptions[0])
    }
  }, [allTriggerOptions, triggerCandidate])

  useEffect(() => {
    if (!toolCandidate && allToolNames.length > 0) {
      setToolCandidate(allToolNames[0])
    }
  }, [allToolNames, toolCandidate])

  const issues = useMemo(() => validateForm(form, rows, selectedIndex), [form, rows, selectedIndex])

  const persist = async (nextRows: AgentRow[], nextSelected: number | null, okMsg: string) => {
    if (!cfg) return

    const agentsObj: Record<string, Record<string, unknown>> = {}
    for (const row of nextRows) {
      const id = row.form.agent_id.trim().toUpperCase()
      agentsObj[id] = serializeAgent({ ...row.form, agent_id: id }, row.raw)
    }

    const payload: SystemConfig = {
      ...cfg,
      agents: agentsObj,
    }

    setSaving(true)
    setError(null)
    setMessage(null)
    try {
      await api.saveSystemConfig(payload)
      setCfg(payload)
      setRows(nextRows)
      setSelectedIndex(nextSelected)
      if (nextSelected !== null && nextRows[nextSelected]) {
        setForm(nextRows[nextSelected].form)
      }
      setMessage(okMsg)
    } catch (err) {
      setError(String(err))
    } finally {
      setSaving(false)
    }
  }

  const handleUpdate = async () => {
    if (selectedIndex === null) {
      setError('No agent selected. Use "Save As New" for a new agent.')
      return
    }
    if (issues.length > 0) {
      setError('Please fix validation issues before updating.')
      return
    }
    const next = [...rows]
    next[selectedIndex] = {
      raw: next[selectedIndex].raw,
      form: { ...form, agent_id: form.agent_id.trim().toUpperCase() },
    }
    await persist(next, selectedIndex, 'Agent updated and saved.')
  }

  const handleSaveAsNew = async () => {
    if (issues.length > 0) {
      setError('Please fix validation issues before saving.')
      return
    }
    const next = [
      ...rows,
      {
        raw: {},
        form: { ...form, agent_id: form.agent_id.trim().toUpperCase() },
      },
    ]
    await persist(next, next.length - 1, 'Agent created and saved.')
  }

  const handleDelete = async () => {
    if (selectedIndex === null) {
      setError('No agent selected to delete.')
      return
    }
    const next = rows.filter((_, idx) => idx !== selectedIndex)
    const nextSel = next.length > 0 ? Math.min(selectedIndex, next.length - 1) : null
    await persist(next, nextSel, 'Agent deleted and saved.')
    if (nextSel === null) {
      setForm({ ...EMPTY_FORM })
    }
  }

  const selectAgent = (idx: number) => {
    setSelectedIndex(idx)
    setForm({ ...rows[idx].form })
    setError(null)
    setMessage(null)
  }

  const setField = <K extends keyof AgentForm>(key: K, value: AgentForm[K]) => {
    setForm(prev => ({ ...prev, [key]: value }))
  }

  const addTrigger = () => {
    if (!triggerCandidate) return
    setForm(prev => ({
      ...prev,
      event_triggers: uniqueSorted([...prev.event_triggers, triggerCandidate]),
    }))
  }

  const removeTrigger = (trigger: string) => {
    setForm(prev => ({
      ...prev,
      event_triggers: prev.event_triggers.filter(t => t !== trigger),
    }))
  }

  const addTool = () => {
    if (!toolCandidate) return
    setForm(prev => ({
      ...prev,
      allowed_tools: uniqueSorted([...prev.allowed_tools, toolCandidate]),
    }))
  }

  const removeTool = (tool: string) => {
    setForm(prev => ({
      ...prev,
      allowed_tools: prev.allowed_tools.filter(t => t !== tool),
    }))
  }

  const summary = useMemo(() => {
    const lines: string[] = []
    lines.push(`ID: ${form.agent_id || '(missing)'}`)
    lines.push(`Type: ${form.type || '(missing)'}`)
    lines.push(`Enabled: ${form.enable ? 'yes' : 'no'}`)
    lines.push(`LLM: ${form.llm || '(missing)'}`)
    lines.push(`Broker: ${form.broker || '(missing)'}`)
    if (form.type === 'AA') lines.push(`Pair: ${form.pair || '(missing)'}`)
    lines.push(`Timer: ${form.timer_enabled ? `on (${form.timer_interval_seconds}s)` : 'off'}`)
    lines.push(`AnyCandle: ${form.any_candle}`)
    lines.push(`Triggers: ${form.event_triggers.length}`)
    lines.push(`Allowed tools: ${form.allowed_tools.length}`)
    return lines.join('\n')
  }, [form])

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between px-4 py-2 bg-gray-900 border-b border-gray-700 flex-shrink-0">
        <span className="text-sm text-gray-300 font-medium">Agent Config Wizard</span>
        <div className="flex items-center gap-3">
          <span className="text-xs text-gray-500">D:\GitHub\GHG\OpenForexAI\config\system.json5 (agents)</span>
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
        {loading && <p className="text-sm text-gray-500 animate-pulse">Loading agent config…</p>}
        {error && <p className="text-sm text-red-400">Error: {error}</p>}
        {message && <p className="text-sm text-emerald-400">{message}</p>}

        {!loading && (
          <>
            <div className="border border-gray-700 rounded overflow-hidden">
              <div className="max-h-[260px] overflow-y-auto">
                <table className="w-full text-xs">
                  <thead className="bg-gray-900 text-gray-300">
                    <tr>
                      <th className="text-left px-2 py-2 w-12">#</th>
                      <th className="text-left px-2 py-2">Agent ID</th>
                      <th className="text-left px-2 py-2 w-14">On</th>
                      <th className="text-left px-2 py-2 w-14">Type</th>
                      <th className="text-left px-2 py-2">LLM</th>
                      <th className="text-left px-2 py-2">Broker</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((r, idx) => (
                      <tr
                        key={`${r.form.agent_id}-${idx}`}
                        onClick={() => selectAgent(idx)}
                        className={[
                          'border-t border-gray-800 cursor-pointer',
                          idx === selectedIndex ? 'bg-emerald-900/20' : 'bg-gray-950 hover:bg-gray-900/50',
                        ].join(' ')}
                      >
                        <td className="px-2 py-1.5 text-gray-500">{idx + 1}</td>
                        <td className="px-2 py-1.5 text-gray-200">{r.form.agent_id}</td>
                        <td className="px-2 py-1.5 text-gray-300">{r.form.enable ? 'Y' : 'N'}</td>
                        <td className="px-2 py-1.5 text-gray-300">{r.form.type}</td>
                        <td className="px-2 py-1.5 text-gray-400">{r.form.llm}</td>
                        <td className="px-2 py-1.5 text-gray-400">{r.form.broker}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            <div className="grid grid-cols-1 xl:grid-cols-3 gap-4 min-h-[420px]">
              <section className="xl:col-span-2 border border-gray-700 rounded p-3 bg-gray-900/40 space-y-3">
                <div className="flex items-center justify-between">
                  <h3 className="text-sm text-gray-200 font-medium">Agent Editor</h3>
                  <button
                    onClick={() => { setSelectedIndex(null); setForm({ ...EMPTY_FORM }); setError(null); setMessage(null) }}
                    className="text-xs px-2 py-1 rounded border border-gray-700 text-gray-300 hover:bg-gray-800"
                  >
                    New Empty Agent
                  </button>
                </div>

                <div className="grid gap-2" style={{ gridTemplateColumns: 'repeat(16, minmax(0, 1fr))' }}>
                  <label title={TIPS.agent_id} className="text-xs text-gray-300 col-span-4">
                    Agent id
                    <input title={TIPS.agent_id} value={form.agent_id} onChange={e => setField('agent_id', e.target.value.toUpperCase())} className="mt-1 w-full bg-gray-800 border border-gray-600 rounded px-2 py-1 text-sm text-gray-200" placeholder="OAPR1-EURUSD-AA-ANLYS" />
                  </label>
                  <label title={TIPS.enable} className="text-xs text-gray-300 col-span-2">
                    Enable
                    <select title={TIPS.enable} value={form.enable ? 'true' : 'false'} onChange={e => setField('enable', e.target.value === 'true')} className="mt-1 w-full bg-gray-800 border border-gray-600 rounded px-2 py-1 text-sm text-gray-200"><option value="true">true</option><option value="false">false</option></select>
                  </label>
                  <label title={TIPS.comment} className="text-xs text-gray-300 col-span-10">
                    Comment
                    <input title={TIPS.comment} value={form.comment} onChange={e => setField('comment', e.target.value)} className="mt-1 w-full bg-gray-800 border border-gray-600 rounded px-2 py-1 text-sm text-gray-200" />
                  </label>

                  <label title={TIPS.pair} className="text-xs text-gray-300 col-span-2">
                    Pair
                    <input title={TIPS.pair} value={form.pair} onChange={e => setField('pair', e.target.value.toUpperCase())} disabled={form.type !== 'AA'} className="mt-1 w-full bg-gray-800 border border-gray-600 rounded px-2 py-1 text-sm text-gray-200 disabled:opacity-50" />
                  </label>
                  <label title={TIPS.type} className="text-xs text-gray-300 col-span-2">
                    Type
                    <select title={TIPS.type} value={form.type} onChange={e => setField('type', e.target.value)} className="mt-1 w-full bg-gray-800 border border-gray-600 rounded px-2 py-1 text-sm text-gray-200"><option value="AA">AA</option><option value="BA">BA</option><option value="GA">GA</option><option value="AD">AD</option></select>
                  </label>
                  <label title={TIPS.llm} className="text-xs text-gray-300 col-span-4">
                    LLM
                    <select title={TIPS.llm} value={form.llm} onChange={e => setField('llm', e.target.value)} className="mt-1 w-full bg-gray-800 border border-gray-600 rounded px-2 py-1 text-sm text-gray-200"><option value="">-- select --</option>{llmNames.map(n => <option key={n} value={n}>{n}</option>)}</select>
                  </label>
                  <label title={TIPS.broker} className="text-xs text-gray-300 col-span-4">
                    Broker
                    <select title={TIPS.broker} value={form.broker} onChange={e => setField('broker', e.target.value)} className="mt-1 w-full bg-gray-800 border border-gray-600 rounded px-2 py-1 text-sm text-gray-200"><option value="">-- select --</option>{brokerNames.map(n => <option key={n} value={n}>{n}</option>)}</select>
                  </label>
                  <div className="col-span-4 grid grid-cols-3 gap-2">
                    <label title={TIPS.timer_enabled} className="text-xs text-gray-300">
                      Timer Enabled
                      <select title={TIPS.timer_enabled} value={form.timer_enabled ? 'true' : 'false'} onChange={e => setField('timer_enabled', e.target.value === 'true')} className="mt-1 w-full bg-gray-800 border border-gray-600 rounded px-2 py-1 text-sm text-gray-200"><option value="false">false</option><option value="true">true</option></select>
                    </label>
                    <label title={TIPS.timer_interval_seconds} className="text-xs text-gray-300">
                      Timer Interval
                      <input title={TIPS.timer_interval_seconds} type="number" value={form.timer_interval_seconds} onChange={e => setField('timer_interval_seconds', Number(e.target.value))} className="mt-1 w-full bg-gray-800 border border-gray-600 rounded px-2 py-1 text-sm text-gray-200" />
                    </label>
                    <label title={TIPS.any_candle} className="text-xs text-gray-300">
                      AnyCandle
                      <input title={TIPS.any_candle} type="number" min={1} step={1} value={form.any_candle} onChange={e => setField('any_candle', Math.max(1, Math.trunc(Number(e.target.value) || 1)))} className="mt-1 w-full bg-gray-800 border border-gray-600 rounded px-2 py-1 text-sm text-gray-200" />
                    </label>
                  </div>
                  <div className="col-span-12" />

                  <label title={TIPS.system_prompt} className="text-xs text-gray-300 col-span-full">
                    System Prompt
                    <textarea title={TIPS.system_prompt} rows={8} value={form.system_prompt} onChange={e => setField('system_prompt', e.target.value)} className="mt-1 w-full bg-gray-800 border border-gray-600 rounded px-2 py-1 text-sm text-gray-200" />
                  </label>

                  <div title={TIPS.event_triggers} className="text-xs text-gray-300 col-span-8">
                    Event Trigger
                    <div className="mt-1 flex gap-2"><select title={TIPS.event_triggers} value={triggerCandidate} onChange={e => setTriggerCandidate(e.target.value)} className="flex-1 bg-gray-800 border border-gray-600 rounded px-2 py-1 text-sm text-gray-200">{allTriggerOptions.map(t => <option key={t} value={t}>{t}</option>)}</select><button title="Add selected event trigger" onClick={addTrigger} className="px-2 py-1 rounded bg-emerald-700 hover:bg-emerald-600 text-white"><Plus className="w-3.5 h-3.5" /></button></div>
                    <div className="mt-2 border border-gray-700 rounded p-2 min-h-[84px] bg-gray-950/60"><div className="flex flex-wrap gap-2">{form.event_triggers.map(t => <span key={t} className="inline-flex items-center gap-1 px-2 py-1 rounded bg-gray-800 text-gray-200">{t}<button title="Remove" onClick={() => removeTrigger(t)} className="text-red-300 hover:text-red-200"><Minus className="w-3.5 h-3.5" /></button></span>)}</div></div>
                  </div>

                  <div title={TIPS.allowed_tools} className="text-xs text-gray-300 col-span-8">
                    Allowed tools
                    <div className="mt-1 flex gap-2"><select title={TIPS.allowed_tools} value={toolCandidate} onChange={e => setToolCandidate(e.target.value)} className="flex-1 bg-gray-800 border border-gray-600 rounded px-2 py-1 text-sm text-gray-200">{allToolNames.map(t => <option key={t} value={t}>{t}</option>)}</select><button title="Add selected tool" onClick={addTool} className="px-2 py-1 rounded bg-emerald-700 hover:bg-emerald-600 text-white"><Plus className="w-3.5 h-3.5" /></button></div>
                    <div className="mt-2 border border-gray-700 rounded p-2 min-h-[84px] bg-gray-950/60"><div className="flex flex-wrap gap-2">{form.allowed_tools.map(t => <span key={t} className="inline-flex items-center gap-1 px-2 py-1 rounded bg-gray-800 text-gray-200">{t}<button title="Remove" onClick={() => removeTool(t)} className="text-red-300 hover:text-red-200"><Minus className="w-3.5 h-3.5" /></button></span>)}</div></div>
                  </div>

                  <label title={TIPS.context_tiers} className="block text-xs text-gray-300 col-span-6 row-span-2">tool_config.context_tiers<textarea title={TIPS.context_tiers} rows={8} value={form.context_tiers_text} onChange={e => setField('context_tiers_text', e.target.value)} className="mt-1 w-full h-[calc(100%-1.6rem)] bg-gray-800 border border-gray-600 rounded px-2 py-1 text-xs text-gray-200 font-mono" /></label>
                  <label title={TIPS.tier_tools} className="block text-xs text-gray-300 col-span-6 row-span-2">tool_config.tier_tools<textarea title={TIPS.tier_tools} rows={8} value={form.tier_tools_text} onChange={e => setField('tier_tools_text', e.target.value)} className="mt-1 w-full h-[calc(100%-1.6rem)] bg-gray-800 border border-gray-600 rounded px-2 py-1 text-xs text-gray-200 font-mono" /></label>
                  <label title={TIPS.max_tool_turns} className="text-xs text-gray-300 col-span-2">max_tool_turns<input title={TIPS.max_tool_turns} type="number" value={form.max_tool_turns} onChange={e => setField('max_tool_turns', Number(e.target.value))} className="mt-1 w-full bg-gray-800 border border-gray-600 rounded px-2 py-1 text-sm text-gray-200" /></label>
                  <div className="col-span-2" />
                  <label title={TIPS.max_tokens} className="text-xs text-gray-300 col-span-2">max_tokens<input title={TIPS.max_tokens} type="number" value={form.max_tokens} onChange={e => setField('max_tokens', Number(e.target.value))} className="mt-1 w-full bg-gray-800 border border-gray-600 rounded px-2 py-1 text-sm text-gray-200" /></label>

                  <div className="col-span-full flex items-center gap-2 pt-1">
                    <button onClick={() => void handleUpdate()} disabled={saving} className="text-xs px-3 py-1.5 rounded bg-emerald-700 hover:bg-emerald-600 text-white disabled:opacity-50 flex items-center gap-1"><Save className="w-3.5 h-3.5" />Update</button>
                    <button onClick={() => void handleSaveAsNew()} disabled={saving} className="text-xs px-3 py-1.5 rounded bg-blue-700 hover:bg-blue-600 text-white disabled:opacity-50">Save As New</button>
                    <button onClick={() => void handleDelete()} disabled={saving || selectedIndex === null} className="text-xs px-3 py-1.5 rounded bg-red-700 hover:bg-red-600 text-white disabled:opacity-50 flex items-center gap-1"><Trash2 className="w-3.5 h-3.5" />Delete</button>
                  </div>
                </div>
              </section>

              <aside className="border border-gray-700 rounded p-3 bg-gray-900/30 space-y-3">
                <div>
                  <h3 className="text-sm text-gray-200 font-medium mb-2">Live Summary</h3>
                  <pre className="text-xs whitespace-pre-wrap text-gray-300 leading-5">{summary}</pre>
                </div>
                <div className="pt-3 border-t border-gray-700">
                  <h4 className="text-xs text-gray-200 font-semibold mb-1">Validation</h4>
                  {issues.length === 0 ? (
                    <p className="text-xs text-emerald-400">No validation issues detected.</p>
                  ) : (
                    <ul className="text-xs text-amber-300 space-y-1">{issues.map(issue => <li key={issue}>- {issue}</li>)}</ul>
                  )}
                </div>
              </aside>
            </div>
          </>
        )}
      </div>
    </div>
  )
}

