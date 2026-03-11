import { useEffect, useMemo, useState } from 'react'
import { Plus, RefreshCw, Save, Trash2 } from 'lucide-react'
import { api } from '@/api/client'

type BridgeTarget = {
  tool_name: string
  description: string
  target_agent_id: string
}

type BridgeToolForm = {
  name: string
  description: string
  timeout_seconds: number
  question_description: string
  mode: 'single' | 'multi'
  target_agent_id: string
  targets: BridgeTarget[]
}

type AgentToolsConfig = Record<string, unknown> & {
  bridge_tools?: unknown[]
}

const EMPTY_TARGET: BridgeTarget = {
  tool_name: '',
  description: '',
  target_agent_id: '',
}

const EMPTY_FORM: BridgeToolForm = {
  name: '',
  description: '',
  timeout_seconds: 90,
  question_description: 'Your specific question or request. Be precise to get a focused answer.',
  mode: 'single',
  target_agent_id: '',
  targets: [{ ...EMPTY_TARGET }],
}

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

function normalizeTarget(raw: unknown): BridgeTarget {
  if (typeof raw === 'string') {
    return {
      ...EMPTY_TARGET,
      target_agent_id: raw,
    }
  }
  if (!raw || typeof raw !== 'object') {
    return { ...EMPTY_TARGET }
  }
  const row = raw as Record<string, unknown>
  return {
    tool_name: toText(row.tool_name || row.name || row.alias),
    description: toText(row.description),
    target_agent_id: toText(row.target_agent_id || row.agent_id),
  }
}

function normalizeBridgeTool(raw: unknown): BridgeToolForm {
  if (!raw || typeof raw !== 'object') return { ...EMPTY_FORM, targets: [{ ...EMPTY_TARGET }] }
  const row = raw as Record<string, unknown>

  const directTargets = Array.isArray(row.targets) ? row.targets.map(normalizeTarget) : []
  const idsTargets = Array.isArray(row.target_agent_ids)
    ? row.target_agent_ids.map(normalizeTarget)
    : []
  const hasMulti = directTargets.length > 0 || idsTargets.length > 0

  const targets = (directTargets.length > 0 ? directTargets : idsTargets)
  const safeTargets = targets.length > 0 ? targets : [{ ...EMPTY_TARGET }]

  return {
    name: toText(row.name),
    description: toText(row.description),
    timeout_seconds: toNum(row.timeout_seconds, 90),
    question_description: toText(row.question_description) || EMPTY_FORM.question_description,
    mode: hasMulti ? 'multi' : 'single',
    target_agent_id: toText(row.target_agent_id),
    targets: safeTargets,
  }
}

function serializeForm(form: BridgeToolForm): Record<string, unknown> {
  const base: Record<string, unknown> = {
    name: form.name.trim(),
    description: form.description.trim(),
    timeout_seconds: form.timeout_seconds,
    question_description: form.question_description.trim(),
  }

  if (form.mode === 'single') {
    base.target_agent_id = form.target_agent_id.trim()
    return base
  }

  base.targets = form.targets.map(t => ({
    tool_name: t.tool_name.trim(),
    description: t.description.trim(),
    target_agent_id: t.target_agent_id.trim(),
  }))
  return base
}

function validateForm(form: BridgeToolForm, all: BridgeToolForm[], selectedIndex: number | null): string[] {
  const issues: string[] = []

  if (!form.name.trim()) issues.push('`name` is required.')
  if (!form.description.trim()) issues.push('`description` is required.')
  if (!Number.isFinite(form.timeout_seconds) || form.timeout_seconds <= 0) {
    issues.push('`timeout_seconds` must be a number greater than 0.')
  }

  const duplicate = all.findIndex((t, idx) => idx !== selectedIndex && t.name.trim() === form.name.trim())
  if (form.name.trim() && duplicate >= 0) {
    issues.push(`Duplicate bridge tool name: "${form.name}" already exists in row ${duplicate + 1}.`)
  }

  if (form.mode === 'single') {
    if (!form.target_agent_id.trim()) issues.push('`target_agent_id` is required for single-target mode.')
  } else {
    if (form.targets.length === 0) issues.push('At least one `targets` entry is required for multi-target mode.')
    const seenToolNames = new Set<string>()
    form.targets.forEach((t, idx) => {
      if (!t.tool_name.trim()) issues.push(`targets[${idx + 1}].tool_name is required.`)
      if (!t.description.trim()) issues.push(`targets[${idx + 1}].description is required.`)
      if (!t.target_agent_id.trim()) issues.push(`targets[${idx + 1}].target_agent_id is required.`)
      const key = t.tool_name.trim().toLowerCase()
      if (key) {
        if (seenToolNames.has(key)) issues.push(`Duplicate targets tool_name: "${t.tool_name}".`)
        seenToolNames.add(key)
      }
    })
  }

  return issues
}

export function BridgeToolsEditor() {
  const [cfg, setCfg] = useState<AgentToolsConfig | null>(null)
  const [tools, setTools] = useState<BridgeToolForm[]>([])
  const [selectedIndex, setSelectedIndex] = useState<number | null>(null)
  const [form, setForm] = useState<BridgeToolForm>({ ...EMPTY_FORM, targets: [{ ...EMPTY_TARGET }] })
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)

  const load = async () => {
    setLoading(true)
    setError(null)
    setMessage(null)
    try {
      const next = await api.getConfigFile('agent_tools') as AgentToolsConfig
      const bridgeRaw = Array.isArray(next.bridge_tools) ? next.bridge_tools : []
      const normalized = bridgeRaw.map(normalizeBridgeTool)
      setCfg(next)
      setTools(normalized)
      if (normalized.length > 0) {
        setSelectedIndex(0)
        setForm(normalized[0])
      } else {
        setSelectedIndex(null)
        setForm({ ...EMPTY_FORM, targets: [{ ...EMPTY_TARGET }] })
      }
    } catch (err) {
      setError(String(err))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { void load() }, [])

  const issues = useMemo(() => validateForm(form, tools, selectedIndex), [form, tools, selectedIndex])

  const summary = useMemo(() => {
    const lines: string[] = []
    lines.push(`Name: ${form.name || '(missing)'}`)
    lines.push(`Mode: ${form.mode}`)
    lines.push(`Timeout: ${form.timeout_seconds}s`)
    lines.push('')
    if (form.mode === 'single') {
      lines.push(`Target: ${form.target_agent_id || '(missing)'}`)
    } else {
      lines.push(`Targets: ${form.targets.length}`)
      form.targets.forEach((t, i) => {
        lines.push(`${i + 1}. ${t.tool_name || '(missing tool_name)'} -> ${t.target_agent_id || '(missing target)'}`)
      })
    }
    return lines.join('\n')
  }, [form])

  const persist = async (nextTools: BridgeToolForm[], nextSelected: number | null, okMsg: string) => {
    if (!cfg) return
    const payload: AgentToolsConfig = {
      ...cfg,
      bridge_tools: nextTools.map(serializeForm),
    }
    setSaving(true)
    setError(null)
    setMessage(null)
    try {
      await api.saveConfigFile('agent_tools', payload)
      setCfg(payload)
      setTools(nextTools)
      setSelectedIndex(nextSelected)
      if (nextSelected !== null && nextTools[nextSelected]) {
        setForm(nextTools[nextSelected])
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
      setError('No bridge tool selected. Use "Save As New" for a new entry.')
      return
    }
    if (issues.length > 0) {
      setError('Please fix validation issues before updating.')
      return
    }
    const next = [...tools]
    next[selectedIndex] = { ...form, targets: form.targets.map(t => ({ ...t })) }
    await persist(next, selectedIndex, 'Bridge tool updated and saved.')
  }

  const handleSaveAsNew = async () => {
    if (issues.length > 0) {
      setError('Please fix validation issues before saving.')
      return
    }
    const next = [...tools, { ...form, targets: form.targets.map(t => ({ ...t })) }]
    await persist(next, next.length - 1, 'Bridge tool created and saved.')
  }

  const handleDelete = async () => {
    if (selectedIndex === null) {
      setError('No bridge tool selected to delete.')
      return
    }
    const next = tools.filter((_, idx) => idx !== selectedIndex)
    const nextSel = next.length > 0 ? Math.min(selectedIndex, next.length - 1) : null
    await persist(next, nextSel, 'Bridge tool deleted and saved.')
    if (nextSel === null) {
      setForm({ ...EMPTY_FORM, targets: [{ ...EMPTY_TARGET }] })
    }
  }

  const selectTool = (idx: number) => {
    setSelectedIndex(idx)
    setForm({ ...tools[idx], targets: tools[idx].targets.map(t => ({ ...t })) })
    setError(null)
    setMessage(null)
  }

  const setField = <K extends keyof BridgeToolForm>(key: K, value: BridgeToolForm[K]) => {
    setForm(prev => ({ ...prev, [key]: value }))
  }

  const setTargetField = (idx: number, key: keyof BridgeTarget, value: string) => {
    setForm(prev => {
      const next = prev.targets.map((t, i) => (i === idx ? { ...t, [key]: value } : t))
      return { ...prev, targets: next }
    })
  }

  const addTarget = () => {
    setForm(prev => ({ ...prev, targets: [...prev.targets, { ...EMPTY_TARGET }] }))
  }

  const removeTarget = (idx: number) => {
    setForm(prev => {
      const next = prev.targets.filter((_, i) => i !== idx)
      return { ...prev, targets: next.length > 0 ? next : [{ ...EMPTY_TARGET }] }
    })
  }

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between px-4 py-2 bg-gray-900 border-b border-gray-700 flex-shrink-0">
        <span className="text-sm text-gray-300 font-medium">Bridge Tools</span>
        <div className="flex items-center gap-3">
          <span className="text-xs text-gray-500">D:\GitHub\GHG\OpenForexAI\config\RunTime\agent_tools.json5 (bridge_tools)</span>
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
        {loading && <p className="text-sm text-gray-500 animate-pulse">Loading bridge tools…</p>}
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
                      <th className="text-left px-2 py-2">Name</th>
                      <th className="text-left px-2 py-2 w-24">Mode</th>
                      <th className="text-left px-2 py-2">Target(s)</th>
                    </tr>
                  </thead>
                  <tbody>
                    {tools.map((t, idx) => (
                      <tr
                        key={`${t.name}-${idx}`}
                        onClick={() => selectTool(idx)}
                        className={[
                          'border-t border-gray-800 cursor-pointer',
                          idx === selectedIndex ? 'bg-emerald-900/20' : 'bg-gray-950 hover:bg-gray-900/50',
                        ].join(' ')}
                      >
                        <td className="px-2 py-1.5 text-gray-500">{idx + 1}</td>
                        <td className="px-2 py-1.5 text-gray-200">{t.name}</td>
                        <td className="px-2 py-1.5 text-gray-300">{t.mode}</td>
                        <td className="px-2 py-1.5 text-gray-400">
                          {t.mode === 'single'
                            ? (t.target_agent_id || '(none)')
                            : `${t.targets.length} target(s)`}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            <div className="grid grid-cols-1 xl:grid-cols-2 gap-4 min-h-[380px]">
              <section className="border border-gray-700 rounded p-3 bg-gray-900/40 space-y-3">
                <div className="flex items-center justify-between">
                  <h3 className="text-sm text-gray-200 font-medium">Bridge Tool Editor</h3>
                  <button
                    onClick={() => { setSelectedIndex(null); setForm({ ...EMPTY_FORM, targets: [{ ...EMPTY_TARGET }] }); setError(null); setMessage(null) }}
                    className="text-xs px-2 py-1 rounded border border-gray-700 text-gray-300 hover:bg-gray-800"
                  >
                    New Empty Tool
                  </button>
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
                    Timeout (seconds)
                    <input
                      type="number"
                      value={form.timeout_seconds}
                      onChange={e => setField('timeout_seconds', Number(e.target.value))}
                      className="mt-1 w-full bg-gray-800 border border-gray-600 rounded px-2 py-1 text-sm text-gray-200"
                    />
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

                <label className="block text-xs text-gray-300">
                  Question Description (shown to LLM)
                  <textarea
                    value={form.question_description}
                    onChange={e => setField('question_description', e.target.value)}
                    rows={2}
                    className="mt-1 w-full bg-gray-800 border border-gray-600 rounded px-2 py-1 text-sm text-gray-200"
                  />
                </label>

                <div className="grid grid-cols-2 gap-2 max-w-[320px]">
                  <button
                    onClick={() => setField('mode', 'single')}
                    className={[
                      'text-xs px-2 py-1.5 rounded border',
                      form.mode === 'single'
                        ? 'border-emerald-500 text-emerald-300 bg-emerald-900/20'
                        : 'border-gray-700 text-gray-300 hover:bg-gray-800',
                    ].join(' ')}
                  >
                    Single Target
                  </button>
                  <button
                    onClick={() => setField('mode', 'multi')}
                    className={[
                      'text-xs px-2 py-1.5 rounded border',
                      form.mode === 'multi'
                        ? 'border-emerald-500 text-emerald-300 bg-emerald-900/20'
                        : 'border-gray-700 text-gray-300 hover:bg-gray-800',
                    ].join(' ')}
                  >
                    Multi Target
                  </button>
                </div>

                {form.mode === 'single' && (
                  <label className="block text-xs text-gray-300">
                    target_agent_id
                    <input
                      value={form.target_agent_id}
                      onChange={e => setField('target_agent_id', e.target.value)}
                      className="mt-1 w-full bg-gray-800 border border-gray-600 rounded px-2 py-1 text-sm text-gray-200"
                      placeholder="GLOBL-ALL___-GA-TA001"
                    />
                  </label>
                )}

                {form.mode === 'multi' && (
                  <div className="space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="text-xs text-gray-300">Targets</span>
                      <button
                        onClick={addTarget}
                        className="text-xs px-2 py-1 rounded border border-gray-700 text-gray-300 hover:bg-gray-800 flex items-center gap-1"
                      >
                        <Plus className="w-3.5 h-3.5" />
                        Add Target
                      </button>
                    </div>
                    {form.targets.map((t, idx) => (
                      <div key={idx} className="border border-gray-700 rounded p-2 bg-gray-950/60 space-y-2">
                        <div className="flex items-center justify-between">
                          <span className="text-xs text-gray-400">Target {idx + 1}</span>
                          <button
                            onClick={() => removeTarget(idx)}
                            className="text-xs px-2 py-0.5 rounded border border-gray-700 text-gray-300 hover:bg-gray-800"
                          >
                            Remove
                          </button>
                        </div>
                        <input
                          value={t.tool_name}
                          onChange={e => setTargetField(idx, 'tool_name', e.target.value)}
                          placeholder="tool_name (e.g. ask_news_agent)"
                          className="w-full bg-gray-800 border border-gray-600 rounded px-2 py-1 text-xs text-gray-200"
                        />
                        <input
                          value={t.target_agent_id}
                          onChange={e => setTargetField(idx, 'target_agent_id', e.target.value)}
                          placeholder="target_agent_id"
                          className="w-full bg-gray-800 border border-gray-600 rounded px-2 py-1 text-xs text-gray-200"
                        />
                        <input
                          value={t.description}
                          onChange={e => setTargetField(idx, 'description', e.target.value)}
                          placeholder="description shown to LLM"
                          className="w-full bg-gray-800 border border-gray-600 rounded px-2 py-1 text-xs text-gray-200"
                        />
                      </div>
                    ))}
                  </div>
                )}

                <div className="flex items-center gap-2 pt-1">
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
                    disabled={saving || selectedIndex === null}
                    className="text-xs px-3 py-1.5 rounded bg-red-700 hover:bg-red-600 text-white disabled:opacity-50 flex items-center gap-1"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                    Delete
                  </button>
                </div>
              </section>

              <aside className="border border-gray-700 rounded p-3 bg-gray-900/30">
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
    </div>
  )
}
