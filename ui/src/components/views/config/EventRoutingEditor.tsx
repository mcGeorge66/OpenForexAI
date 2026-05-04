import { useEffect, useMemo, useState } from 'react'
import { RefreshCw, Save, Trash2 } from 'lucide-react'
import { api } from '@/api/client'

type RoutingRule = {
  id: string
  description?: string
  event: string
  from: string
  to: string
  priority: number
}

type RoutingConfig = Record<string, unknown> & {
  rules?: RoutingRule[]
}

const EMPTY_RULE: RoutingRule = {
  id: '',
  description: '',
  event: '',
  from: '*',
  to: '@handlers',
  priority: 100,
}

function classifyTarget(to: string): string {
  if (to === '@handlers') return 'Only legacy handlers receive this event.'
  if (to === '*') return 'Broadcast to all registered agents.'
  if (to.includes('{sender.}')) return 'Invalid template token.'
  if (to.includes('{sender.')) return 'Template target: parts are derived from the sender agent ID.'
  if (to.includes('*')) return 'Pattern broadcast: event is fanned out to all matching agent IDs.'
  return 'Direct delivery to one specific agent ID.'
}

function looksLikeAgentExpr(value: string): boolean {
  if (!value) return false
  if (value === '*' || value === '@handlers') return true
  const replaced = value
    .replace(/\{sender\.[a-z_]+\}/gi, 'X')
  const parts = replaced.split('-')
  return parts.length >= 4 && parts[0].length > 0 && parts[1].length > 0 && parts[2].length > 0 && parts[3].length > 0
}

function validateRule(rule: RoutingRule, allRules: RoutingRule[], selectedIndex: number | null): string[] {
  const issues: string[] = []
  if (!rule.id.trim()) issues.push('`id` is required.')
  if (!rule.event.trim()) issues.push('`event` is required.')
  if (!rule.from.trim()) issues.push('`from` is required.')
  if (!rule.to.trim()) issues.push('`to` is required.')
  if (!Number.isFinite(rule.priority)) issues.push('`priority` must be a number.')

  if (rule.from && !looksLikeAgentExpr(rule.from)) {
    issues.push('`from` does not look like a valid pattern/expression for the current `-` ID format.')
  }
  if (rule.to && !looksLikeAgentExpr(rule.to)) {
    issues.push('`to` does not look like a valid target/pattern/template for the current `-` ID format.')
  }
  if (rule.id.trim()) {
    const dup = allRules.findIndex((r, idx) => r.id === rule.id && idx !== selectedIndex)
    if (dup >= 0) issues.push(`Duplicate id: "${rule.id}" already exists in row ${dup + 1}.`)
  }
  if (rule.to.includes('{sender.') && !rule.from.includes('-')) {
    issues.push('Template target with `{sender.*}` is usually used with structured sender IDs.')
  }
  return issues
}

export function EventRoutingEditor() {
  const [cfg, setCfg] = useState<RoutingConfig | null>(null)
  const [rules, setRules] = useState<RoutingRule[]>([])
  const [selectedIndex, setSelectedIndex] = useState<number | null>(null)
  const [form, setForm] = useState<RoutingRule>(EMPTY_RULE)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [focusedField, setFocusedField] = useState<keyof RoutingRule | null>(null)

  const load = async () => {
    setLoading(true)
    setError(null)
    setMessage(null)
    try {
      const next = await api.getConfigFile('event_routing') as RoutingConfig
      const nextRules = Array.isArray(next.rules) ? next.rules : []
      setCfg(next)
      setRules(nextRules)
      if (nextRules.length > 0) {
        setSelectedIndex(0)
        setForm(nextRules[0])
      } else {
        setSelectedIndex(null)
        setForm(EMPTY_RULE)
      }
    } catch (err) {
      setError(String(err))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { void load() }, [])

  const issues = useMemo(
    () => validateRule(form, rules, selectedIndex),
    [form, rules, selectedIndex],
  )

  const summary = useMemo(() => {
    const lines: string[] = []
    lines.push(`Event: "${form.event || '(missing)'}"`)
    lines.push(`From: "${form.from || '(missing)'}"`)
    lines.push(`To: "${form.to || '(missing)'}"`)
    lines.push(`Priority: ${form.priority}`)
    lines.push('')
    lines.push(classifyTarget(form.to))
    return lines.join('\n')
  }, [form])

  const fieldHelp = useMemo(() => {
    const map: Record<string, string> = {
      id: 'Unique technical rule key. Use stable snake_case, e.g. "m5_candle_to_matching_aa". Must be unique across all rules.',
      event: 'Event type value from backend (e.g. "m5_candle_available", "signal_generated", "*" for all events). Exact spelling matters.',
      description: 'Optional human-readable explanation for maintainers. Keep it short and specific.',
      from: 'Sender pattern in Agent-ID format with "-" segments (e.g. "*-*-AA-*"). Use "*" wildcards carefully.',
      to: 'Target expression: literal agent id, wildcard pattern, template like "{sender.broker}-ALL___-BA-*", "*" (all), or "@handlers".',
      priority: 'Lower number = higher priority (executed earlier). Typical values: 1-200. Keep related rules grouped.',
    }
    if (!focusedField) return 'Focus an input field to see guidance here.'
    return map[focusedField] ?? 'Focus an input field to see guidance here.'
  }, [focusedField])

  const persist = async (nextRules: RoutingRule[], nextSelected: number | null, okMsg: string) => {
    if (!cfg) return
    const payload: RoutingConfig = { ...cfg, rules: nextRules }
    setSaving(true)
    setError(null)
    setMessage(null)
    try {
      await api.saveConfigFile('event_routing', payload)
      setCfg(payload)
      setRules(nextRules)
      setSelectedIndex(nextSelected)
      if (nextSelected !== null && nextRules[nextSelected]) {
        setForm(nextRules[nextSelected])
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
      setError('No rule selected. Use "Save As New" for a new rule.')
      return
    }
    if (issues.length > 0) {
      setError('Please fix validation issues before updating.')
      return
    }
    const next = [...rules]
    next[selectedIndex] = { ...form }
    await persist(next, selectedIndex, 'Rule updated and saved.')
  }

  const handleSaveAsNew = async () => {
    if (issues.length > 0) {
      setError('Please fix validation issues before saving.')
      return
    }
    const next = [...rules, { ...form }]
    await persist(next, next.length - 1, 'Rule created and saved.')
  }

  const handleDelete = async () => {
    if (selectedIndex === null) {
      setError('No rule selected to delete.')
      return
    }
    const next = rules.filter((_, idx) => idx !== selectedIndex)
    const nextSel = next.length > 0 ? Math.min(selectedIndex, next.length - 1) : null
    await persist(next, nextSel, 'Rule deleted and saved.')
    if (nextSel === null) setForm(EMPTY_RULE)
  }

  const selectRule = (idx: number) => {
    setSelectedIndex(idx)
    setForm(rules[idx])
    setError(null)
    setMessage(null)
  }

  const setField = <K extends keyof RoutingRule>(key: K, value: RoutingRule[K]) => {
    setForm(prev => ({ ...prev, [key]: value }))
  }

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between px-4 py-2 bg-gray-900 border-b border-gray-700 flex-shrink-0">
        <span className="text-sm text-gray-300 font-medium">Event Routing Rules</span>
        <div className="flex items-center gap-3">
          <span className="text-xs text-gray-500">D:\\GitHub\\GHG\\OpenForexAI\\config\\RunTime\\event_routing.json5</span>
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
        {loading && <p className="text-sm text-gray-500 animate-pulse">Loading routing rules…</p>}
        {error && <p className="text-sm text-red-400">Error: {error}</p>}
        {message && <p className="text-sm text-emerald-400">{message}</p>}

        {!loading && (
          <>
            <div className="border border-gray-700 rounded overflow-hidden">
              <div className="max-h-[320px] overflow-y-auto">
              <table className="w-full text-xs">
                <thead className="bg-gray-900 text-gray-300">
                  <tr>
                    <th className="text-left px-2 py-2 w-12">#</th>
                    <th className="text-left px-2 py-2">ID</th>
                    <th className="text-left px-2 py-2">Event</th>
                    <th className="text-left px-2 py-2">From</th>
                    <th className="text-left px-2 py-2">To</th>
                    <th className="text-left px-2 py-2 w-16">Prio</th>
                  </tr>
                </thead>
                <tbody>
                  {rules.map((r, idx) => (
                    <tr
                      key={`${r.id}-${idx}`}
                      onClick={() => selectRule(idx)}
                      className={[
                        'border-t border-gray-800 cursor-pointer',
                        idx === selectedIndex ? 'bg-emerald-900/20' : 'bg-gray-950 hover:bg-gray-900/50',
                      ].join(' ')}
                    >
                      <td className="px-2 py-1.5 text-gray-500">{idx + 1}</td>
                      <td className="px-2 py-1.5 text-gray-200">{r.id}</td>
                      <td className="px-2 py-1.5 text-gray-300">{r.event}</td>
                      <td className="px-2 py-1.5 text-gray-400">{r.from}</td>
                      <td className="px-2 py-1.5 text-gray-400">{r.to}</td>
                      <td className="px-2 py-1.5 text-gray-400">{r.priority}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              </div>
            </div>

            <div className="grid grid-cols-1 xl:grid-cols-2 gap-4 min-h-[360px]">
              <section className="border border-gray-700 rounded p-3 bg-gray-900/40 space-y-3">
                <div className="flex items-center justify-between">
                  <h3 className="text-sm text-gray-200 font-medium">Rule Editor</h3>
                  <button
                    onClick={() => { setSelectedIndex(null); setForm(EMPTY_RULE); setError(null); setMessage(null) }}
                    className="text-xs px-2 py-1 rounded border border-gray-700 text-gray-300 hover:bg-gray-800"
                  >
                    New Empty Rule
                  </button>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <label className="text-xs text-gray-300">
                  ID
                  <input
                    value={form.id}
                    onChange={e => setField('id', e.target.value)}
                    onFocus={() => setFocusedField('id')}
                    className="mt-1 w-full bg-gray-800 border border-gray-600 rounded px-2 py-1 text-sm text-gray-200"
                  />
                </label>
                <label className="text-xs text-gray-300">
                  Event
                  <input
                    value={form.event}
                    onChange={e => setField('event', e.target.value)}
                    onFocus={() => setFocusedField('event')}
                    className="mt-1 w-full bg-gray-800 border border-gray-600 rounded px-2 py-1 text-sm text-gray-200"
                  />
                </label>
                </div>

                <label className="block text-xs text-gray-300">
                  Description
                  <input
                    value={form.description ?? ''}
                    onChange={e => setField('description', e.target.value)}
                    onFocus={() => setFocusedField('description')}
                    className="mt-1 w-full bg-gray-800 border border-gray-600 rounded px-2 py-1 text-sm text-gray-200"
                  />
                </label>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <label className="text-xs text-gray-300">
                  From
                  <input
                    value={form.from}
                    onChange={e => setField('from', e.target.value)}
                    onFocus={() => setFocusedField('from')}
                    className="mt-1 w-full bg-gray-800 border border-gray-600 rounded px-2 py-1 text-sm text-gray-200"
                  />
                </label>
                <label className="text-xs text-gray-300">
                  To
                  <input
                    value={form.to}
                    onChange={e => setField('to', e.target.value)}
                    onFocus={() => setFocusedField('to')}
                    className="mt-1 w-full bg-gray-800 border border-gray-600 rounded px-2 py-1 text-sm text-gray-200"
                  />
                </label>
              </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-3 pt-2">
                  <div>
                    <label className="block text-xs text-gray-300 max-w-[200px]">
                      Priority
                      <input
                        type="number"
                        value={form.priority}
                        onChange={e => setField('priority', Number(e.target.value))}
                        onFocus={() => setFocusedField('priority')}
                        className="mt-1 w-full bg-gray-800 border border-gray-600 rounded px-2 py-1 text-sm text-gray-200"
                      />
                    </label>

                    <div className="flex items-center gap-2 pt-2">
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
                  </div>
                  <div className="border border-gray-700 rounded bg-gray-950/50 p-2">
                    <p className="text-xs text-gray-300 leading-5 whitespace-pre-wrap">{fieldHelp}</p>
                  </div>
                </div>
              </section>

              <aside className="border border-gray-700 rounded p-3 bg-gray-900/30">
                <h3 className="text-sm text-gray-200 font-medium mb-2">Live Rule Explanation</h3>
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

