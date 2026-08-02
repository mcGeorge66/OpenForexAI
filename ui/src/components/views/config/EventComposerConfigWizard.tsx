/**
 * EventComposerConfigWizard — CRUD for EC (EventComposer) entities.
 *
 * Parallel to AgentConfigWizard but for EC entities.
 * EC entities use a Script tab (ScriptEditor) and a Config (JSON) tab
 * (Json5MonacoEditor) instead of a prompt field.
 */

import { useEffect, useMemo, useState } from 'react'
import { ChevronDown, ChevronRight, Clock, Copy, Download, MessageSquare, Save, Trash2, Plus, Play } from 'lucide-react'
import { api, type ToolInfo, type ECExecuteResponse } from '@/api/client'
import { ScriptEditor } from '@/components/common/ScriptEditor'
import { Json5MonacoEditor } from '@/components/common/Json5MonacoEditor'
import { AiAssistantModal } from '@/components/common/AiAssistantModal'
import { EventTestModal } from '@/components/views/events/EventTestModal'
import { EntityAssistantPanel } from '@/components/common/EntityAssistantPanel'
import { EntityHistoryModal } from '@/components/common/EntityHistoryModal'
import { useMonitoringStream } from '@/hooks/useMonitoringStream'

// ─── Types ───────────────────────────────────────────────────────────────────

type SystemConfig = Record<string, unknown> & {
  modules?: { llm?: Record<string, string>; broker?: Record<string, string> }
  agents?: Record<string, Record<string, unknown>>
  event_composers?: Record<string, Record<string, unknown>>
  snapshot_profiles?: Record<string, Record<string, unknown>>
}

type ECForm = {
  ec_id: string
  comment: string
  enable: boolean
  broker: string
  pair: string
  timer_enabled: boolean
  timer_interval_seconds: number
  any_candle: number
  event_triggers: string[]
  session_filter: Array<{ session: string; pre: number; post: number }>
  allowed_tools: string[]
  max_tool_turns: number
  script_timeout_seconds: number
  script: string
  config_json: string
  pass_trigger: boolean
  // Optional named snapshot_profiles entry — when set, the script gets a pre-built
  // `snapshot` global (same assembled snapshot an Agent would get), instead of/in
  // addition to calling tools itself.
  snapshot_profile: string
}

type ECRow = {
  raw: Record<string, unknown>
  form: ECForm
}

const EC_ID_RE = /^[A-Z0-9_]{5}-[A-Z0-9_]{6}-EC-[A-Z0-9]{1,5}(?:-.+)?$/
const TIMER_TRIGGER = 'timer'

const DEFAULT_EVENT_TRIGGERS = [
  'm5_candle_trigger',
  'prompt_updated',
  'agent_query',
  'analysis_result',
  'signal_generated',
  'account_status_updated',
  'ec_output',
]

const EMPTY_FORM: ECForm = {
  ec_id: '',
  comment: '',
  enable: true,
  broker: '',
  pair: '',
  timer_enabled: false,
  timer_interval_seconds: 60,
  any_candle: 1,
  event_triggers: ['m5_candle_trigger'],
  session_filter: [],
  allowed_tools: [],
  max_tool_turns: 5,
  script_timeout_seconds: 60,
  script: 'async def main(input, config, tools):\n    # EC script\n    return None\n',
  config_json: '{}',
  pass_trigger: false,
  snapshot_profile: '',
}

function toText(v: unknown): string {
  return typeof v === 'string' ? v : ''
}

function toNum(v: unknown, fallback: number): number {
  if (typeof v === 'number' && Number.isFinite(v)) return v
  if (typeof v === 'string') { const n = Number(v); if (Number.isFinite(n)) return n }
  return fallback
}

function toBool(v: unknown, fallback: boolean): boolean {
  return typeof v === 'boolean' ? v : fallback
}

function toStringList(v: unknown): string[] {
  if (!Array.isArray(v)) return []
  return v.map(x => String(x).trim()).filter(Boolean)
}

function rawToForm(ec_id: string, raw: Record<string, unknown>): ECForm {
  const timer = raw.timer && typeof raw.timer === 'object' ? raw.timer as Record<string, unknown> : {}
  const tc = raw.tool_config && typeof raw.tool_config === 'object' ? raw.tool_config as Record<string, unknown> : {}
  const sf = Array.isArray(raw.session_filter) ? raw.session_filter : []

  const backendTriggers = toStringList(raw.event_triggers)
  const uiTriggers = backendTriggers.includes(TIMER_TRIGGER) ? backendTriggers : backendTriggers
  const timerEnabled = toBool(timer.enabled, false)
  const displayTriggers = timerEnabled
    ? [...new Set([...uiTriggers, TIMER_TRIGGER])]
    : uiTriggers.filter(t => t !== TIMER_TRIGGER)

  let config_json_str = '{}'
  const cj = raw.config_json
  if (typeof cj === 'string') {
    config_json_str = cj
  } else if (cj && typeof cj === 'object') {
    try { config_json_str = JSON.stringify(cj, null, 2) } catch { /* ignore */ }
  }

  return {
    ec_id,
    comment: toText(raw.comment),
    enable: toBool(raw.enable, true),
    broker: toText(raw.broker),
    pair: toText(raw.pair),
    timer_enabled: timerEnabled,
    timer_interval_seconds: toNum(timer.interval_seconds, 60),
    any_candle: toNum(raw.AnyCandle, 1),
    event_triggers: displayTriggers,
    session_filter: sf.map((s: unknown) => {
      const o = s && typeof s === 'object' ? s as Record<string, unknown> : {}
      return { session: toText(o.session), pre: toNum(o.pre, 0), post: toNum(o.post, 0) }
    }),
    allowed_tools: toStringList(tc.allowed_tools),
    max_tool_turns: toNum(tc.max_tool_turns, 5),
    script_timeout_seconds: toNum(tc.script_timeout_seconds, 60),
    script: toText(raw.script),
    config_json: config_json_str,
    pass_trigger: toBool(raw.pass_trigger, false),
    snapshot_profile: toText(raw.snapshot_profile),
  }
}

function formToRaw(form: ECForm): Record<string, unknown> {
  const backendTriggers = form.event_triggers.filter(t => t !== TIMER_TRIGGER)
  return {
    ...(form.comment ? { comment: form.comment } : {}),
    enable: form.enable,
    ...(form.broker ? { broker: form.broker } : {}),
    ...(form.pair ? { pair: form.pair } : {}),
    ...(form.snapshot_profile.trim() ? { snapshot_profile: form.snapshot_profile.trim() } : {}),
    timer: {
      enabled: form.timer_enabled,
      interval_seconds: form.timer_interval_seconds,
    },
    AnyCandle: form.any_candle,
    event_triggers: backendTriggers,
    session_filter: form.session_filter,
    tool_config: {
      allowed_tools: form.allowed_tools,
      max_tool_turns: form.max_tool_turns,
      script_timeout_seconds: form.script_timeout_seconds,
    },
    pass_trigger: form.pass_trigger,
    script: form.script,
    config_json: form.config_json,
  }
}

// ─── Main Component ───────────────────────────────────────────────────────────

export function EventComposerConfigWizard() {
  const [systemConfig, setSystemConfig] = useState<SystemConfig | null>(null)
  const [allTools, setAllTools] = useState<ToolInfo[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [saveMsg, setSaveMsg] = useState<string | null>(null)
  const [saveError, setSaveError] = useState<string | null>(null)

  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [editForm, setEditForm] = useState<ECForm | null>(null)
  const [isNew, setIsNew] = useState(false)

  // Script/Config tab state
  const [activeTab, setActiveTab] = useState<'script' | 'config' | 'test'>('script')
  const [triggersOpen, setTriggersOpen] = useState(false)
  const [toolsOpen, setToolsOpen] = useState(false)
  const [configJsonError, setConfigJsonError] = useState<string | null>(null)

  // Test panel
  const [testInput, setTestInput] = useState('{}')
  const [testRunning, setTestRunning] = useState(false)
  const [testResult, setTestResult] = useState<ECExecuteResponse | null>(null)
  const [testError, setTestError] = useState<string | null>(null)
  const [exampleLoading, setExampleLoading] = useState<string | null>(null)
  const [exampleError, setExampleError] = useState<string | null>(null)
  const debugStream = useMonitoringStream({ filter: ['ec_debug_log'] })
  const debugEntries = debugStream.events.filter(e => e.payload.ec_id === editForm?.ec_id)

  async function loadRealExample(eventType: string) {
    setExampleLoading(eventType)
    setExampleError(null)
    try {
      const events = await api.getEvents({ event_type: eventType, limit: 1 })
      if (events.length === 0) {
        setExampleError(`No real "${eventType}" event found in the event log yet.`)
        return
      }
      setTestInput(JSON.stringify(events[0].payload, null, 2))
    } catch (e) {
      setExampleError(String(e))
    } finally {
      setExampleLoading(null)
    }
  }
  const [aiAssistantOpen, setAiAssistantOpen] = useState(false)
  const [testModalOpen, setTestModalOpen] = useState(false)
  const [historyOpen, setHistoryOpen] = useState(false)

  useEffect(() => {
    setLoading(true)
    Promise.all([api.getSystemConfig(), api.getTools()])
      .then(([cfg, toolsResp]) => {
        setSystemConfig(cfg as SystemConfig)
        setAllTools(toolsResp.tools)
        setLoading(false)
      })
      .catch(err => {
        setError(String(err))
        setLoading(false)
      })
  }, [])

  const brokerNames = useMemo(() => Object.keys(systemConfig?.modules?.broker ?? {}), [systemConfig])
  const snapshotProfileNames = useMemo(() => Object.keys(systemConfig?.snapshot_profiles ?? {}), [systemConfig])
  const pairNames = useMemo(() => {
    const pairs = new Set<string>()
    for (const cfg of Object.values(systemConfig?.agents ?? {})) {
      const p = (cfg as Record<string, unknown>).pair
      if (typeof p === 'string' && p.trim()) pairs.add(p.trim())
    }
    return [...pairs].sort()
  }, [systemConfig])

  const ecRows: ECRow[] = useMemo(() => {
    if (!systemConfig?.event_composers) return []
    return Object.entries(systemConfig.event_composers).map(([id, raw]) => ({
      raw,
      form: rawToForm(id, raw),
    }))
  }, [systemConfig])

  // ── Save to server ────────────────────────────────────────────────────────

  async function persistConfig(updated: SystemConfig) {
    setSaving(true)
    setSaveMsg(null)
    setSaveError(null)
    try {
      await api.saveSystemConfig(updated)
      setSystemConfig(updated)
      setSaveMsg('Saved.')
    } catch (err) {
      setSaveError(String(err))
    } finally {
      setSaving(false)
    }
  }

  // ── EC selection ──────────────────────────────────────────────────────────

  function selectEC(id: string) {
    const row = ecRows.find(r => r.form.ec_id === id)
    if (!row) return
    setSelectedId(id)
    setEditForm({ ...row.form })
    setIsNew(false)
    setActiveTab('script')
    setConfigJsonError(null)
    setSaveMsg(null)
    setSaveError(null)
    setTestResult(null)
    setTestError(null)
  }

  function startNew() {
    setSelectedId(null)
    setEditForm({ ...EMPTY_FORM })
    setIsNew(true)
    setActiveTab('script')
    setConfigJsonError(null)
    setSaveMsg(null)
    setSaveError(null)
    setTestResult(null)
    setTestError(null)
  }

  async function handleTest(): Promise<ECExecuteResponse | null> {
    if (!editForm) return null
    let input: Record<string, unknown> = {}
    try { input = JSON.parse(testInput) } catch {
      setTestError('Input JSON is invalid.')
      return null
    }
    setTestRunning(true)
    setTestResult(null)
    setTestError(null)
    debugStream.clear()
    try {
      const result = await api.executeComposer(editForm.ec_id, input)
      setTestResult(result)
      return result
    } catch (err) {
      setTestError(String(err))
      return null
    } finally {
      setTestRunning(false)
    }
  }

  // ── Validation helpers ────────────────────────────────────────────────────

  function validateForm(f: ECForm): string | null {
    if (!EC_ID_RE.test(f.ec_id)) return 'EC ID must match XXXXX-XXXXXX-EC-NAME format (TYPE must be EC).'
    if (isNew && ecRows.some(r => r.form.ec_id === f.ec_id)) return `EC ID "${f.ec_id}" already exists.`
    return null
  }

  function validateConfigJson(json: string): string | null {
    try { JSON.parse(json); return null }
    catch (e) { return `Invalid JSON: ${String(e)}` }
  }

  // ── Save EC ───────────────────────────────────────────────────────────────

  async function handleSave() {
    if (!editForm || !systemConfig) return
    const formError = validateForm(editForm)
    if (formError) { setSaveError(formError); return }
    const jsonError = validateConfigJson(editForm.config_json)
    if (jsonError) {
      setConfigJsonError(jsonError)
      setActiveTab('config')
      setSaveError('Config JSON is invalid — please fix it before saving.')
      return
    }
    const raw = formToRaw(editForm)
    const updated: SystemConfig = {
      ...systemConfig,
      event_composers: {
        ...(systemConfig.event_composers ?? {}),
        [editForm.ec_id]: raw,
      },
    }
    await persistConfig(updated)
    if (isNew) { setSelectedId(editForm.ec_id); setIsNew(false) }
    // Trigger config reload so the running EC picks up changes without a restart
    try {
      await api.injectEvent({
        event_type: 'ec_config_requested',
        source_agent_id: editForm.ec_id,
        target_agent_id: 'SYSTM-ALL___-GA-CFGSV',
        payload: { ec_id: editForm.ec_id },
      })
    } catch {
      // Non-fatal — EC will pick up changes on next restart if inject fails
    }
  }

  // ── Delete EC ─────────────────────────────────────────────────────────────

  async function handleDelete() {
    if (!selectedId || !systemConfig) return
    if (!window.confirm(`Delete EC "${selectedId}"?`)) return
    const composers = { ...(systemConfig.event_composers ?? {}) }
    delete composers[selectedId]
    await persistConfig({ ...systemConfig, event_composers: composers })
    setSelectedId(null)
    setEditForm(null)
    setIsNew(false)
  }

  // ── Form helpers ──────────────────────────────────────────────────────────

  function setField<K extends keyof ECForm>(key: K, value: ECForm[K]) {
    setEditForm(f => f ? { ...f, [key]: value } : f)
    setSaveMsg(null)
    setSaveError(null)
  }

  function toggleTrigger(t: string) {
    if (!editForm) return
    const has = editForm.event_triggers.includes(t)
    const next = has ? editForm.event_triggers.filter(x => x !== t) : [...editForm.event_triggers, t]
    if (t === TIMER_TRIGGER) setField('timer_enabled', !has)
    setField('event_triggers', next)
  }

  function toggleTool(name: string) {
    if (!editForm) return
    const has = editForm.allowed_tools.includes(name)
    setField('allowed_tools', has ? editForm.allowed_tools.filter(t => t !== name) : [...editForm.allowed_tools, name])
  }

  // ─── Render ───────────────────────────────────────────────────────────────

  if (loading) return <div className="p-6 text-gray-400 text-sm">Loading…</div>
  if (error) return <div className="p-6 text-red-400 text-sm">Error: {error}</div>

  return (
    <>
    <div className="flex h-full overflow-hidden">
      {/* ── Left panel: EC list ── */}
      <aside className="w-56 flex-shrink-0 bg-gray-900 border-r border-gray-700 flex flex-col">
        <div className="flex items-center justify-between px-3 py-2 border-b border-gray-700">
          <span className="text-xs font-semibold text-white uppercase tracking-wide">EventComposers</span>
          <button
            onClick={startNew}
            title="New EventComposer"
            className="text-gray-500 hover:text-emerald-400 transition-colors"
          >
            <Plus className="w-3.5 h-3.5" />
          </button>
        </div>
        <ul className="flex-1 overflow-y-auto py-1">
          {ecRows.map(row => (
            <li key={row.form.ec_id}>
              <button
                onClick={() => selectEC(row.form.ec_id)}
                className={[
                  'w-full text-left px-3 py-2 text-xs transition-colors border-l-2',
                  selectedId === row.form.ec_id && !isNew
                    ? 'bg-emerald-900/40 text-emerald-300 border-emerald-400'
                    : 'text-white hover:text-gray-200 hover:bg-gray-800 border-transparent',
                ].join(' ')}
              >
                <div className="font-mono">{row.form.ec_id}</div>
                {row.form.comment && (
                  <div className="text-gray-500 truncate mt-0.5">{row.form.comment}</div>
                )}
                {!row.form.enable && (
                  <div className="text-orange-500 text-xs mt-0.5">disabled</div>
                )}
              </button>
            </li>
          ))}
          {isNew && (
            <li>
              <div className="px-3 py-2 text-xs text-emerald-400 border-l-2 border-emerald-400 bg-emerald-900/20">
                + New EC
              </div>
            </li>
          )}
        </ul>
      </aside>

      {/* ── Right panel: form ── */}
      {editForm ? (
        <div className="flex-1 overflow-y-auto">
          <div className="max-w-3xl mx-auto p-6 space-y-6">

            {/* Header */}
            <div className="flex items-center justify-between">
              <div>
                <h2 className="text-sm font-semibold text-gray-200">
                  {isNew ? 'New EventComposer' : editForm.ec_id}
                </h2>
                <p className="text-xs text-white mt-0.5">
                  Script-based entity — peer to LLM agents
                </p>
              </div>
              <div className="flex items-center gap-2">
                {!isNew && (
                  <button
                    onClick={() => setHistoryOpen(true)}
                    className="flex items-center gap-1 px-3 py-1.5 text-xs rounded bg-gray-700 hover:bg-gray-600 text-gray-200 transition-colors border border-gray-500/40"
                    title="History"
                  >
                    <Clock className="w-3.5 h-3.5" />
                    History
                  </button>
                )}
                <button
                  onClick={() => setTestModalOpen(true)}
                  className="flex items-center gap-1 px-3 py-1.5 text-xs rounded bg-emerald-700 hover:bg-emerald-600 text-white transition-colors border border-emerald-500/40"
                  title="Test Event"
                >
                  <Play className="w-3.5 h-3.5" />
                  Test Event
                </button>
                <button
                  onClick={() => setAiAssistantOpen(true)}
                  className="flex items-center gap-1 px-3 py-1.5 text-xs rounded bg-indigo-700 hover:bg-indigo-600 text-white transition-colors border border-indigo-500/40"
                  title="AI Assistant"
                >
                  <MessageSquare className="w-3.5 h-3.5" />
                  AI Assistant
                </button>
                {!isNew && (
                  <button
                    onClick={() => void handleDelete()}
                    disabled={saving}
                    className="flex items-center gap-1 px-3 py-1.5 text-xs rounded bg-red-600 hover:bg-red-500 text-white transition-colors disabled:opacity-40"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                    Delete
                  </button>
                )}
                <button
                  onClick={() => void handleSave()}
                  disabled={saving}
                  className="flex items-center gap-1 px-3 py-1.5 text-xs rounded bg-emerald-600 hover:bg-emerald-500 text-white transition-colors disabled:opacity-40"
                >
                  <Save className="w-3.5 h-3.5" />
                  {saving ? 'Saving…' : 'Save'}
                </button>
              </div>
            </div>

            {saveMsg && <div className="text-xs text-emerald-400">{saveMsg}</div>}
            {saveError && <div className="text-xs text-red-400">{saveError}</div>}

            {/* Identity */}
            <section className="space-y-3">
              <h3 className="text-xs font-semibold text-white uppercase tracking-wide">Identity</h3>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs text-white mb-1">EC ID *</label>
                  <input
                    value={editForm.ec_id}
                    onChange={e => setField('ec_id', e.target.value.toUpperCase())}
                    disabled={!isNew}
                    placeholder="GLOBL-ALL___-EC-ECHO"
                    className="w-full bg-gray-800 text-gray-200 text-xs font-mono px-2 py-1.5 rounded border border-gray-600 focus:outline-none focus:border-emerald-500 disabled:opacity-50"
                  />
                  <p className="text-xs text-white mt-1">BROKER(5)-PAIR(6)-EC-NAME(1-5)</p>
                </div>
                <div>
                  <label className="block text-xs text-white mb-1">Comment</label>
                  <input
                    value={editForm.comment}
                    onChange={e => setField('comment', e.target.value)}
                    className="w-full bg-gray-800 text-gray-200 text-xs px-2 py-1.5 rounded border border-gray-600 focus:outline-none focus:border-emerald-500"
                  />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs text-white mb-1">Broker module</label>
                  <select
                    value={editForm.broker}
                    onChange={e => setField('broker', e.target.value)}
                    className="w-full bg-gray-800 text-gray-200 text-xs font-mono px-2 py-1.5 rounded border border-gray-600 focus:outline-none focus:border-emerald-500"
                  >
                    <option value="">— optional —</option>
                    {brokerNames.map(n => <option key={n} value={n}>{n}</option>)}
                  </select>
                  <p className="text-xs text-white mt-1">Resolves broker_name for tools</p>
                </div>
                <div>
                  <label className="block text-xs text-white mb-1">Pair</label>
                  <select
                    value={editForm.pair}
                    onChange={e => setField('pair', e.target.value)}
                    className="w-full bg-gray-800 text-gray-200 text-xs font-mono px-2 py-1.5 rounded border border-gray-600 focus:outline-none focus:border-emerald-500"
                  >
                    <option value="">— optional —</option>
                    {pairNames.map(n => <option key={n} value={n}>{n}</option>)}
                  </select>
                  <p className="text-xs text-white mt-1">Fallback when not in input JSON</p>
                </div>
              </div>
              <div>
                <label className="block text-xs text-white mb-1" title="Optional named snapshot_profiles entry. When set, the script receives a pre-built `snapshot` global — the same assembled snapshot (tool_blocks/calculation_blocks/assembly_transform_script) an Agent would get, instead of/in addition to calling tools itself.">
                  Snapshot Profile
                </label>
                <select
                  value={editForm.snapshot_profile}
                  onChange={e => setField('snapshot_profile', e.target.value)}
                  className="w-1/2 bg-gray-800 text-gray-200 text-xs font-mono px-2 py-1.5 rounded border border-gray-600 focus:outline-none focus:border-emerald-500"
                >
                  <option value="">— none —</option>
                  {snapshotProfileNames.map(n => <option key={n} value={n}>{n}</option>)}
                </select>
                <p className="text-xs text-white mt-1">Injects a `snapshot` global into the script — see Snapshot Config.</p>
              </div>
              <label className="flex items-center gap-2 text-xs text-white cursor-pointer">
                <input
                  type="checkbox"
                  checked={editForm.enable}
                  onChange={e => setField('enable', e.target.checked)}
                  className="w-3 h-3"
                />
                Enabled
              </label>
            </section>

            {/* Triggers + Session Filter — collapsible */}
            <section className="border border-gray-700 rounded">
              <button
                type="button"
                onClick={() => setTriggersOpen(v => !v)}
                className="w-full flex items-center gap-2 px-3 py-2 text-xs text-white hover:text-gray-200 hover:bg-gray-800/60 transition-colors select-none"
              >
                {triggersOpen
                  ? <ChevronDown className="w-3.5 h-3.5 flex-shrink-0" />
                  : <ChevronRight className="w-3.5 h-3.5 flex-shrink-0" />
                }
                <span className="font-semibold uppercase tracking-wide flex-1 text-left">Kickoff Triggers &amp; Session Filter</span>
                {!triggersOpen && (
                  <span className="text-gray-600 font-mono normal-case tracking-normal">
                    {editForm.event_triggers.join(', ') || '—'}
                    {editForm.session_filter.length > 0 && ` · ${editForm.session_filter.length} session filter`}
                  </span>
                )}
              </button>

              {triggersOpen && (
                <div className="px-3 pb-4 space-y-5 border-t border-gray-700">

                  {/* Triggers */}
                  <div className="space-y-3 pt-3">
                    <h4 className="text-xs font-semibold text-white uppercase tracking-wide">Triggers</h4>
                    <div className="flex flex-wrap gap-2">
                      {[TIMER_TRIGGER, ...DEFAULT_EVENT_TRIGGERS].map(t => (
                        <button
                          key={t}
                          type="button"
                          onClick={() => toggleTrigger(t)}
                          className={[
                            'px-2 py-1 text-xs rounded border transition-colors',
                            editForm.event_triggers.includes(t)
                              ? 'bg-emerald-900/40 text-emerald-300 border-emerald-600'
                              : 'text-white border-gray-700 hover:text-gray-300',
                          ].join(' ')}
                        >
                          {t}
                        </button>
                      ))}
                    </div>
                    {editForm.timer_enabled && (
                      <div className="flex items-center gap-3">
                        <label className="text-xs text-white">Interval (s)</label>
                        <input
                          type="number"
                          min={1}
                          value={editForm.timer_interval_seconds}
                          onChange={e => setField('timer_interval_seconds', Number(e.target.value))}
                          className="w-24 bg-gray-800 text-gray-200 text-xs px-2 py-1 rounded border border-gray-600 focus:outline-none focus:border-emerald-500"
                        />
                      </div>
                    )}
                    {editForm.event_triggers.includes('m5_candle_trigger') && (
                      <div className="flex items-center gap-3">
                        <label className="text-xs text-white">AnyCandle (run every Nth M5)</label>
                        <input
                          type="number"
                          min={1}
                          value={editForm.any_candle}
                          onChange={e => setField('any_candle', Math.max(1, Number(e.target.value)))}
                          className="w-20 bg-gray-800 text-gray-200 text-xs px-2 py-1 rounded border border-gray-600 focus:outline-none focus:border-emerald-500"
                        />
                      </div>
                    )}
                  </div>

                  {/* Divider */}
                  <div className="border-t border-gray-700/60" />

                  {/* Session Filter */}
                  <div className="space-y-3">
                    <div className="flex items-center justify-between">
                      <h4 className="text-xs font-semibold text-white uppercase tracking-wide">Session Filter</h4>
                      <button
                        type="button"
                        onClick={() => setField('session_filter', [...editForm.session_filter, { session: 'london', pre: 0, post: 0 }])}
                        className="text-xs text-white hover:text-emerald-400 transition-colors"
                      >
                        + Add
                      </button>
                    </div>
                    {editForm.session_filter.length === 0 && (
                      <p className="text-xs text-white">No filter — triggers fire in any session.</p>
                    )}
                    {editForm.session_filter.map((sf, idx) => (
                      <div key={idx} className="flex items-center gap-2">
                        <input
                          value={sf.session}
                          onChange={e => {
                            const next = [...editForm.session_filter]
                            next[idx] = { ...sf, session: e.target.value }
                            setField('session_filter', next)
                          }}
                          placeholder="london"
                          className="w-28 bg-gray-800 text-gray-200 text-xs px-2 py-1 rounded border border-gray-600 focus:outline-none focus:border-emerald-500"
                        />
                        <span className="text-xs text-white">pre</span>
                        <input
                          type="number"
                          value={sf.pre}
                          onChange={e => {
                            const next = [...editForm.session_filter]
                            next[idx] = { ...sf, pre: Number(e.target.value) }
                            setField('session_filter', next)
                          }}
                          className="w-16 bg-gray-800 text-gray-200 text-xs px-2 py-1 rounded border border-gray-600 focus:outline-none focus:border-emerald-500"
                        />
                        <span className="text-xs text-white">post</span>
                        <input
                          type="number"
                          value={sf.post}
                          onChange={e => {
                            const next = [...editForm.session_filter]
                            next[idx] = { ...sf, post: Number(e.target.value) }
                            setField('session_filter', next)
                          }}
                          className="w-16 bg-gray-800 text-gray-200 text-xs px-2 py-1 rounded border border-gray-600 focus:outline-none focus:border-emerald-500"
                        />
                        <button
                          type="button"
                          onClick={() => setField('session_filter', editForm.session_filter.filter((_, i) => i !== idx))}
                          className="text-gray-600 hover:text-red-400 transition-colors"
                        >
                          ×
                        </button>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </section>

            {/* Tools — collapsible, takes a lot of vertical space when tool count grows */}
            <section className="border border-gray-700 rounded">
              <button
                type="button"
                onClick={() => setToolsOpen(v => !v)}
                className="w-full flex items-center gap-2 px-3 py-2 text-xs text-white hover:text-gray-200 hover:bg-gray-800/60 transition-colors select-none"
              >
                {toolsOpen
                  ? <ChevronDown className="w-3.5 h-3.5 flex-shrink-0" />
                  : <ChevronRight className="w-3.5 h-3.5 flex-shrink-0" />
                }
                <span className="font-semibold uppercase tracking-wide flex-1 text-left">Allowed Tools</span>
                {!toolsOpen && (
                  <span className="text-gray-600 font-mono normal-case tracking-normal">
                    {editForm.allowed_tools.length > 0 ? `${editForm.allowed_tools.length} selected` : '—'}
                  </span>
                )}
              </button>

              {toolsOpen && (
                <div className="px-3 pb-4 space-y-3 border-t border-gray-700 pt-3">
                  <div className="flex flex-wrap gap-2">
                    {allTools.map(t => (
                      <button
                        key={t.name}
                        type="button"
                        onClick={() => toggleTool(t.name)}
                        title={t.description}
                        className={[
                          'px-2 py-1 text-xs rounded border transition-colors',
                          editForm.allowed_tools.includes(t.name)
                            ? 'bg-emerald-900/40 text-emerald-300 border-emerald-600'
                            : 'text-white border-gray-700 hover:text-gray-300',
                        ].join(' ')}
                      >
                        {t.name}
                      </button>
                    ))}
                  </div>
                  <div className="flex items-center gap-6">
                    <div className="flex items-center gap-2">
                      <label className="text-xs text-white">Max tool turns</label>
                      <input
                        type="number"
                        min={1}
                        value={editForm.max_tool_turns}
                        onChange={e => setField('max_tool_turns', Number(e.target.value))}
                        className="w-20 bg-gray-800 text-gray-200 text-xs px-2 py-1 rounded border border-gray-600 focus:outline-none focus:border-emerald-500"
                      />
                    </div>
                    <div className="flex items-center gap-2">
                      <label className="text-xs text-white">Script timeout (s)</label>
                      <input
                        type="number"
                        min={0}
                        value={editForm.script_timeout_seconds}
                        onChange={e => setField('script_timeout_seconds', Number(e.target.value))}
                        className="w-20 bg-gray-800 text-gray-200 text-xs px-2 py-1 rounded border border-gray-600 focus:outline-none focus:border-emerald-500"
                      />
                      <span className="text-xs text-white">0 = no timeout</span>
                    </div>
                  </div>
                </div>
              )}
            </section>


            {/* Entity Assistant */}
            <EntityAssistantPanel
              script={editForm.script}
              configJson={editForm.config_json}
              allowedTools={editForm.allowed_tools}
              testInput={testInput}
              testResult={testResult}
              snapshotProfile={editForm.snapshot_profile}
              onApplyScript={v => setField('script', v)}
              onApplyConfig={v => setField('config_json', v)}
              onRunTest={handleTest}
            />

            {/* Script + Config tabs */}
            <section className="space-y-2">
              <div className="flex items-center gap-1 border-b border-gray-700">
                <button
                  onClick={() => setActiveTab('script')}
                  className={[
                    'px-3 py-1.5 text-xs transition-colors',
                    activeTab === 'script'
                      ? 'text-emerald-300 border-b-2 border-emerald-400 -mb-px'
                      : 'text-white hover:text-gray-300',
                  ].join(' ')}
                >
                  Script
                </button>
                <button
                  onClick={() => setActiveTab('config')}
                  className={[
                    'px-3 py-1.5 text-xs transition-colors',
                    activeTab === 'config'
                      ? 'text-emerald-300 border-b-2 border-emerald-400 -mb-px'
                      : 'text-white hover:text-gray-300',
                  ].join(' ')}
                >
                  Config (JSON)
                </button>
                {!isNew && (
                  <button
                    onClick={() => setActiveTab('test')}
                    className={[
                      'px-3 py-1.5 text-xs transition-colors flex items-center gap-1',
                      activeTab === 'test'
                        ? 'text-emerald-300 border-b-2 border-emerald-400 -mb-px'
                        : 'text-white hover:text-gray-300',
                    ].join(' ')}
                  >
                    <Play className="w-3 h-3" />
                    Test
                  </button>
                )}
              </div>

              {activeTab === 'script' && (
                <div>
                  <p className="text-xs text-white mb-1">
                    Define <code className="text-gray-300">async def main(input, config, tools)</code>.
                    Return <code className="text-gray-300">dict</code> to emit output, <code className="text-gray-300">None</code> to skip.
                  </p>
                  <ScriptEditor
                    value={editForm.script}
                    onChange={v => setField('script', v ?? '')}
                    minHeight={400}
                    snippetScope="ec"
                    contextFile="script_ec_context.md"
                  />
                </div>
              )}

              {activeTab === 'config' && (
                <div>
                  <p className="text-xs text-white mb-1">
                    Passed as <code className="text-gray-300">config</code> to the script. Must be valid JSON.
                  </p>
                  <div style={{ height: 400 }} className="border border-gray-600 rounded overflow-hidden">
                    <Json5MonacoEditor
                      value={editForm.config_json}
                      onChange={v => {
                        setField('config_json', v ?? '{}')
                        setConfigJsonError(null)
                      }}
                    />
                  </div>
                  {configJsonError && (
                    <div className="text-xs text-red-400 mt-1">{configJsonError}</div>
                  )}
                </div>
              )}

              {activeTab === 'test' && (
                <div className="space-y-3">
                  <p className="text-xs text-white">
                    Passes the JSON below as <code className="text-gray-300">input</code> to the script.
                    The currently saved <code className="text-gray-300">config_json</code> is used as <code className="text-gray-300">config</code>.
                  </p>
                  {editForm.event_triggers.filter(t => t !== TIMER_TRIGGER).length > 0 && (
                    <div className="flex flex-wrap items-center gap-1.5">
                      <span className="text-xs text-white">Load real example:</span>
                      {editForm.event_triggers.filter(t => t !== TIMER_TRIGGER).map(t => (
                        <button
                          key={t}
                          onClick={() => void loadRealExample(t)}
                          disabled={exampleLoading !== null}
                          className="flex items-center gap-1 px-2 py-1 text-xs bg-gray-800 text-gray-300 border border-gray-700 rounded hover:bg-gray-700 hover:text-white transition-colors disabled:opacity-40"
                          title={`Load the most recent real "${t}" event from the event log`}
                        >
                          <Download className="w-3 h-3" />
                          {exampleLoading === t ? 'Loading…' : t}
                        </button>
                      ))}
                    </div>
                  )}
                  {exampleError && (
                    <div className="text-xs text-amber-400 bg-amber-900/20 rounded p-2">{exampleError}</div>
                  )}
                  <div style={{ height: 200 }} className="border border-gray-600 rounded overflow-hidden">
                    <Json5MonacoEditor
                      value={testInput}
                      onChange={v => setTestInput(v ?? '{}')}
                    />
                  </div>
                  <button
                    onClick={() => void handleTest()}
                    disabled={testRunning}
                    className="flex items-center gap-1.5 px-3 py-1.5 text-xs bg-emerald-800/50 text-emerald-300 border border-emerald-700 rounded hover:bg-emerald-800/80 transition-colors disabled:opacity-40"
                  >
                    <Play className="w-3 h-3" />
                    {testRunning ? 'Running…' : 'Run'}
                  </button>
                  {(debugEntries.length > 0 || testRunning) && (
                    <div>
                      <div className="flex items-center justify-between mb-1">
                        <span className="text-xs text-white">
                          Debug output {testRunning && <span className="text-emerald-400">(live)</span>}
                        </span>
                        <span className="text-xs text-white">
                          via <code className="text-gray-400">debug(message)</code> — test runs only
                        </span>
                      </div>
                      <div className="text-xs font-mono bg-gray-900 rounded p-2 overflow-auto max-h-64 space-y-1">
                        {debugEntries.length === 0 && testRunning && (
                          <span className="text-gray-600 italic">Waiting for debug() calls…</span>
                        )}
                        {debugEntries.map(e => {
                          const line = e.payload.line
                          const elapsed = e.payload.elapsed_seconds
                          const msg = e.payload.message
                          const text = typeof msg === 'object' && msg !== null
                            ? JSON.stringify(msg, null, 2)
                            : String(msg)
                          return (
                            <div key={e.id} className="border-b border-gray-800 pb-1 last:border-0">
                              <span className="text-indigo-400">L{String(line ?? '?')}</span>
                              <span className="text-gray-600"> [{typeof elapsed === 'number' ? elapsed.toFixed(2) : '?'}s]: </span>
                              <span className="text-gray-300 whitespace-pre-wrap break-all">{text}</span>
                            </div>
                          )
                        })}
                      </div>
                    </div>
                  )}
                  {testError && (
                    <div className="text-xs text-red-400 bg-red-900/20 rounded p-2">{testError}</div>
                  )}
                  {testResult && (
                    <div className="space-y-2">
                      <div className="flex items-center gap-2 text-xs">
                        <span className={testResult.success ? 'text-emerald-400' : 'text-red-400'}>
                          {testResult.success ? '✓ Success' : '✗ Failed'}
                        </span>
                        <span className="text-gray-600">{testResult.latency_ms.toFixed(0)} ms</span>
                      </div>
                      {testResult.error && (
                        <div className="text-xs text-red-400 bg-red-900/20 rounded p-2 font-mono whitespace-pre-wrap">
                          {testResult.error}
                        </div>
                      )}
                      <div>
                        <div className="flex items-center justify-between mb-1">
                          <span className="text-xs text-white">Output</span>
                          <button
                            onClick={() => {
                              const text = testResult.output !== null
                                ? JSON.stringify(testResult.output, null, 2)
                                : '(no output)'
                              void navigator.clipboard.writeText(text)
                            }}
                            className="flex items-center gap-1 text-xs text-white hover:text-gray-200 transition-colors"
                            title="Copy output"
                          >
                            <Copy className="w-3 h-3" />
                            Copy
                          </button>
                        </div>
                        <pre className="text-xs text-gray-300 bg-gray-900 rounded p-3 overflow-auto max-h-64 font-mono whitespace-pre-wrap break-all">
                          {testResult.output !== null
                            ? JSON.stringify(testResult.output, null, 2)
                            : '(no output — script returned None)'}
                        </pre>
                      </div>
                    </div>
                  )}
                </div>
              )}
            </section>


          </div>
        </div>
      ) : (
        <div className="flex-1 flex items-center justify-center text-gray-600 text-sm">
          Select an EventComposer or create a new one
        </div>
      )}
    </div>

    {testModalOpen && (
      <EventTestModal
        defaultSourceAgentId={editForm?.ec_id ?? 'management_api'}
        defaultEventType={editForm?.event_triggers?.[0] ?? ''}
        onClose={() => setTestModalOpen(false)}
      />
    )}

    {historyOpen && editForm && (
      <EntityHistoryModal
        entityType="event_composer"
        entityId={editForm.ec_id}
        onClose={() => setHistoryOpen(false)}
      />
    )}

    {aiAssistantOpen && (
      <AiAssistantModal
        title="AI Assistant — Entity Config"
        contextFile="entity_config_assistant.md"
        contextData={editForm ? JSON.stringify(editForm, null, 2) : undefined}
        contextDataLabel={editForm?.ec_id || 'new entity'}
        onClose={() => setAiAssistantOpen(false)}
      />
    )}
    </>
  )
}
