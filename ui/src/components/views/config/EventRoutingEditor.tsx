import { useEffect, useMemo, useState } from 'react'
import { RefreshCw, Save, Trash2, ChevronUp, ChevronDown, ChevronsUpDown, MessageSquare } from 'lucide-react'
import { api } from '@/api/client'
import { useProjectRoot, joinPath } from '@/api/useProjectRoot'

type RoutingRule = {
  id: string
  description?: string
  comment?: string
  event: string
  from: string
  to: string
  priority: number
  disable?: boolean
}

type RoutingConfig = Record<string, unknown> & {
  rules?: RoutingRule[]
}

const EMPTY_RULE: RoutingRule = {
  id: '',
  description: '',
  comment: '',
  event: '',
  from: '*',
  to: '@handlers',
  priority: 100,
  disable: false,
}

// ── All known event types ────────────────────────────────────────────────────
const ALL_EVENT_TYPES = [
  '*',
  // Market data
  'm5_candle_update',
  'm5_candle_trigger',
  'm5_trigger_counter',
  'candle_gap_detected',
  'candle_repair_requested',
  'candle_repair_completed',
  'candle_data_bulk',
  'm5_candle_saved',
  // Indicators / data queries
  'candles_request',
  'candles_response',
  'indicator_request',
  'indicator_response',
  'swing_levels_request',
  'swing_levels_response',
  // Account / positions
  'account_status_updated',
  'account_status_request',
  'account_status_response',
  'positions_request',
  'positions_response',
  // Trading
  'signal_generated',
  'signal_approved',
  'signal_rejected',
  'order_placed',
  'position_opened',
  'position_closed',
  'risk_breach',
  'order_request',
  'order_result',
  'position_close_request',
  'position_close_result',
  'order_modify_request',
  'order_modify_result',
  'order_book_sync_discrepancy',
  'order_book_close_reasoning',
  // Analysis / agents
  'analysis_requested',
  'analysis_result',
  'agent_query',
  'agent_query_response',
  'agent_config_requested',
  'agent_config_response',
  // Event Composers
  'ec_config_requested',
  'ec_config_response',
  'ec_output',
  // LLM
  'llm_request',
  'llm_response',
  // Repository
  'repo_request',
  'repo_response',
  // System
  'optimization_complete',
  'prompt_updated',
  'routing_reload_requested',
]

// ── Event catalogue: what it is and who generates it ────────────────────────
interface EventInfo { what: string; generatedBy: string }
const EVENT_CATALOGUE: Record<string, EventInfo> = {
  '*':                         { what: 'Matches every event type',                         generatedBy: 'n/a — wildcard' },
  m5_candle_update:            { what: 'New M5 candle received and stored',                generatedBy: 'Broker Adapter (AD)' },
  m5_candle_trigger:           { what: 'M5 candle triggers an agent/EC cycle',             generatedBy: 'Broker Adapter (AD)' },
  m5_trigger_counter:          { what: 'Counter emitted per M5 trigger for monitoring',   generatedBy: 'AA Agent' },
  candle_gap_detected:         { what: 'Gap detected in M5 candle sequence',               generatedBy: 'DataContainer (GA-DATA)' },
  candle_repair_requested:     { what: 'Request to fill a candle gap from broker',         generatedBy: 'DataContainer (GA-DATA)' },
  candle_repair_completed:     { what: 'Candle gap successfully filled',                   generatedBy: 'DataContainer (GA-DATA)' },
  candle_data_bulk:            { what: 'Bulk candle data delivered from broker',           generatedBy: 'Broker Adapter (AD)' },
  m5_candle_saved:             { what: 'M5 candle persisted to database',                  generatedBy: 'DataContainer (GA-DATA)' },
  candles_request:             { what: 'Request for OHLCV candle series',                  generatedBy: 'Tool: get_candles (via agent or EC)' },
  candles_response:            { what: 'OHLCV candle series delivered',                    generatedBy: 'DataContainer (GA-DATA)' },
  indicator_request:           { what: 'Request for computed indicator values',            generatedBy: 'Tool: calculate_indicator' },
  indicator_response:          { what: 'Indicator values delivered',                       generatedBy: 'DataContainer (GA-DATA)' },
  swing_levels_request:        { what: 'Request for S/R swing level computation',          generatedBy: 'Tool: get_swing_levels' },
  swing_levels_response:       { what: 'Swing levels and nearest S/R delivered',           generatedBy: 'DataContainer (GA-DATA)' },
  account_status_updated:      { what: 'Account balance/margin polled and saved',          generatedBy: 'Broker Adapter (AD)' },
  account_status_request:      { what: 'Request for current account status',               generatedBy: 'Tool: get_account_status' },
  account_status_response:     { what: 'Account status data delivered',                    generatedBy: 'Broker Adapter (AD)' },
  positions_request:           { what: 'Request for list of open positions',               generatedBy: 'Tool: get_open_positions' },
  positions_response:          { what: 'Open positions list delivered',                    generatedBy: 'Broker Adapter (AD)' },
  signal_generated:            { what: 'Tradeable signal with BIAS and order_start YES',   generatedBy: 'AA Agent' },
  signal_approved:             { what: 'Signal cleared by risk validation',                generatedBy: 'BA Agent or supervisor' },
  signal_rejected:             { what: 'Signal blocked by risk or quality check',          generatedBy: 'BA Agent or supervisor' },
  order_placed:                { what: 'Order successfully placed at broker',              generatedBy: 'Broker Adapter (AD)' },
  position_opened:             { what: 'Position confirmed open by broker',                generatedBy: 'Broker Adapter (AD)' },
  position_closed:             { what: 'Position confirmed closed by broker',              generatedBy: 'Broker Adapter (AD)' },
  risk_breach:                 { what: 'Risk limit breached',                              generatedBy: 'BA Agent or risk module' },
  order_request:               { what: 'Request to place a new order at broker',           generatedBy: 'Tool: place_order / auto_place_order' },
  order_result:                { what: 'Order execution result from broker',               generatedBy: 'Broker Adapter (AD)' },
  position_close_request:      { what: 'Request to close an open position',               generatedBy: 'Tool: close_position' },
  position_close_result:       { what: 'Position close result from broker',               generatedBy: 'Broker Adapter (AD)' },
  order_modify_request:        { what: 'Request to modify SL/TP of an existing order',    generatedBy: 'Tool: modify_order' },
  order_modify_result:         { what: 'Order modification result from broker',           generatedBy: 'Broker Adapter (AD)' },
  order_book_sync_discrepancy: { what: 'Local order book differs from broker state',      generatedBy: 'Broker Adapter (AD) sync loop' },
  order_book_close_reasoning:  { what: 'Agent provides reasoning for a broker-closed position', generatedBy: 'BA Agent' },
  analysis_requested:          { what: 'External request for market analysis',             generatedBy: 'Management API or another agent' },
  analysis_result:             { what: 'Completed AA market analysis published',           generatedBy: 'AA Agent' },
  agent_query:                 { what: 'Direct free-text question to a specific agent',    generatedBy: 'Management API or another agent' },
  agent_query_response:        { what: 'Agent response to a direct query',                 generatedBy: 'Any Agent' },
  agent_config_requested:      { what: 'Agent requests its config from ConfigService',     generatedBy: 'Any Agent (AA/BA/GA) on startup' },
  agent_config_response:       { what: 'ConfigService delivers agent config',              generatedBy: 'ConfigService (GA-CFGSV)' },
  ec_config_requested:         { what: 'Event Composer requests its config',               generatedBy: 'Any Event Composer (EC) on startup' },
  ec_config_response:          { what: 'ConfigService delivers EC config',                 generatedBy: 'ConfigService (GA-CFGSV)' },
  ec_output:                   { what: 'Event Composer published a result',                generatedBy: 'Any Event Composer (EC)' },
  llm_request:                 { what: 'LLM completion request sent via event bus',        generatedBy: 'Any Agent or EC (via llm_helpers)' },
  llm_response:                { what: 'LLM Service returns completion result',            generatedBy: 'LLMService (llm:{module_name})' },
  repo_request:                { what: 'Database read/write operation requested',          generatedBy: 'Any tool or agent (via repo_request helper)' },
  repo_response:               { what: 'Database operation result delivered',              generatedBy: 'RepositoryService (GA-REPO)' },
  optimization_complete:       { what: 'Optimization cycle completed',                     generatedBy: 'Optimization GA agent' },
  prompt_updated:              { what: 'System prompt was updated — agents should reload', generatedBy: 'Management API' },
  routing_reload_requested:    { what: 'Routing rules hot-reload triggered',               generatedBy: 'Management API or any bus member' },
}

// ── Target / From classifiers ────────────────────────────────────────────────
function classifyTarget(to: string): string {
  if (!to) return ''
  if (to === '@handlers') return 'Legacy handler delivery (avoid for new rules).'
  if (to === '*') return 'Broadcast — delivered to every registered bus member.'
  if (to.includes('{sender.')) return 'Template target — parts are derived from the sender ID at dispatch time.'
  if (to.includes('*')) return 'Pattern broadcast — fanned out to all matching agent IDs.'
  return 'Direct delivery to one specific agent ID.'
}

function classifyFrom(from: string): string {
  if (!from) return ''
  if (from === '*') return 'Accepts from any bus member.'
  if (from.includes('*')) return 'Wildcard pattern — matches all sender IDs that fit the format.'
  return 'Restricted to this exact sender ID.'
}

function looksLikeAgentExpr(value: string): boolean {
  if (!value) return false
  if (value === '*' || value === '@handlers') return true
  const replaced = value.replace(/\{sender\.[a-z_]+\}/gi, 'X')
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
  if (rule.from && !looksLikeAgentExpr(rule.from))
    issues.push('`from` does not look like a valid pattern/expression.')
  if (rule.to && !looksLikeAgentExpr(rule.to))
    issues.push('`to` does not look like a valid target/pattern/template.')
  if (rule.id.trim()) {
    const dup = allRules.findIndex((r, idx) => r.id === rule.id && idx !== selectedIndex)
    if (dup >= 0) issues.push(`Duplicate id: "${rule.id}" already exists in row ${dup + 1}.`)
  }
  if (rule.to.includes('{sender.') && !rule.from.includes('-'))
    issues.push('Template target with `{sender.*}` is usually paired with a structured sender pattern.')
  return issues
}

export function EventRoutingEditor() {
  const root = useProjectRoot()
  const [cfg, setCfg] = useState<RoutingConfig | null>(null)
  const [rules, setRules] = useState<RoutingRule[]>([])
  const [selectedIndex, setSelectedIndex] = useState<number | null>(null)
  const [form, setForm] = useState<RoutingRule>(EMPTY_RULE)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [focusedField, setFocusedField] = useState<keyof RoutingRule | null>(null)

  type SortCol = 'id' | 'event' | 'from' | 'to' | 'priority'
  const [sortCol, setSortCol] = useState<SortCol | null>(null)
  const [sortAsc, setSortAsc] = useState(true)
  const [filters, setFilters] = useState({ id: '', event: '', from: '', to: '' })

  const handleSort = (col: SortCol) => {
    if (sortCol === col) setSortAsc(a => !a)
    else { setSortCol(col); setSortAsc(true) }
  }

  const setFilter = (key: keyof typeof filters, val: string) =>
    setFilters(prev => ({ ...prev, [key]: val }))

  const visibleRows = useMemo(() => {
    const f = filters
    let rows = rules.map((r, idx) => ({ r, idx }))
    if (f.id)    rows = rows.filter(({ r }) => r.id.toLowerCase().includes(f.id.toLowerCase()))
    if (f.event) rows = rows.filter(({ r }) => r.event.toLowerCase().includes(f.event.toLowerCase()))
    if (f.from)  rows = rows.filter(({ r }) => r.from.toLowerCase().includes(f.from.toLowerCase()))
    if (f.to)    rows = rows.filter(({ r }) => r.to.toLowerCase().includes(f.to.toLowerCase()))
    if (sortCol) {
      rows = [...rows].sort((a, b) => {
        const av = sortCol === 'priority' ? a.r.priority : String(a.r[sortCol] ?? '')
        const bv = sortCol === 'priority' ? b.r.priority : String(b.r[sortCol] ?? '')
        if (typeof av === 'number' && typeof bv === 'number') return sortAsc ? av - bv : bv - av
        return sortAsc ? String(av).localeCompare(String(bv)) : String(bv).localeCompare(String(av))
      })
    }
    return rows
  }, [rules, filters, sortCol, sortAsc])

  const load = async () => {
    setLoading(true); setError(null); setMessage(null)
    try {
      const next = await api.getConfigFile('event_routing') as RoutingConfig
      const nextRules = Array.isArray(next.rules) ? next.rules : []
      setCfg(next); setRules(nextRules)
      if (nextRules.length > 0) { setSelectedIndex(0); setForm(nextRules[0]) }
      else { setSelectedIndex(null); setForm(EMPTY_RULE) }
    } catch (err) { setError(String(err)) }
    finally { setLoading(false) }
  }

  useEffect(() => { void load() }, [])

  const issues = useMemo(() => validateRule(form, rules, selectedIndex), [form, rules, selectedIndex])

  const fieldHelp = useMemo(() => {
    const map: Record<string, string> = {
      id:          'Unique rule key in snake_case, e.g. "m5_candle_to_aa". Must be unique across all rules.',
      event:       'Select the event type this rule matches. Choose "*" to match all events.',
      description: 'Optional human-readable explanation. Keep it short and specific.',
      comment:     'Persönliche Notizen zu dieser Regel. Hat keinen Einfluss auf das Routing — reine Dokumentation für dich.',
      from:        'Sender pattern using the Agent-ID format (segments separated by "-"). Use "*" as wildcard per segment, e.g. "*-*-AA-*" for all AA agents.',
      to:          'Target: literal agent ID, wildcard pattern, template like "{sender.broker}-ALL___-BA-*", "*" (all), or "@handlers".',
      priority:    'Lower = higher priority. Typical range: 1–200. Rules are evaluated in order.',
    }
    if (!focusedField) return 'Click any field to see guidance.'
    return map[focusedField] ?? 'Click any field to see guidance.'
  }, [focusedField])

  const persist = async (nextRules: RoutingRule[], nextSelected: number | null, okMsg: string) => {
    if (!cfg) return
    const payload: RoutingConfig = { ...cfg, rules: nextRules }
    setSaving(true); setError(null); setMessage(null)
    try {
      await api.saveConfigFile('event_routing', payload)
      setCfg(payload); setRules(nextRules); setSelectedIndex(nextSelected)
      if (nextSelected !== null && nextRules[nextSelected]) setForm(nextRules[nextSelected])
      setMessage(okMsg)
    } catch (err) { setError(String(err)) }
    finally { setSaving(false) }
  }

  const handleUpdate = async () => {
    if (selectedIndex === null) { setError('No rule selected. Use "Save As New" for a new rule.'); return }
    if (issues.length > 0) { setError('Please fix validation issues before updating.'); return }
    const next = [...rules]; next[selectedIndex] = { ...form }
    await persist(next, selectedIndex, 'Rule updated and saved.')
  }

  const handleSaveAsNew = async () => {
    if (issues.length > 0) { setError('Please fix validation issues before saving.'); return }
    const next = [...rules, { ...form }]
    await persist(next, next.length - 1, 'Rule created and saved.')
  }

  const handleDelete = async () => {
    if (selectedIndex === null) { setError('No rule selected to delete.'); return }
    const next = rules.filter((_, idx) => idx !== selectedIndex)
    const nextSel = next.length > 0 ? Math.min(selectedIndex, next.length - 1) : null
    await persist(next, nextSel, 'Rule deleted and saved.')
    if (nextSel === null) setForm(EMPTY_RULE)
  }

  const selectRule = (idx: number) => {
    setSelectedIndex(idx); setForm(rules[idx]); setError(null); setMessage(null)
  }

  const setField = <K extends keyof RoutingRule>(key: K, value: RoutingRule[K]) =>
    setForm(prev => ({ ...prev, [key]: value }))

  // ── Live Rule Explanation ──────────────────────────────────────────────────
  const eventInfo = EVENT_CATALOGUE[form.event]

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between px-4 py-2 bg-gray-900 border-b border-gray-700 flex-shrink-0">
        <span className="text-sm text-gray-300 font-medium">Event Routing Rules</span>
        <div className="flex items-center gap-3">
          <span className="text-xs text-gray-500">{root ? joinPath(root, 'config', 'RunTime', 'event_routing.json5') : 'config/RunTime/event_routing.json5'}</span>
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
            {/* ── Rules table ── */}
            <div className="border border-gray-700 rounded overflow-hidden">
              <div className="max-h-[360px] overflow-y-auto">
              <table className="w-full text-xs">
                <thead className="bg-gray-900 text-gray-300 sticky top-0 z-10">
                  <tr>
                    <th className="text-left px-2 py-2 w-10 bg-gray-900">#</th>
                    {(['id', 'event', 'from', 'to'] as const).map(col => (
                      <th key={col} className="text-left px-2 py-0 bg-gray-900">
                        <button onClick={() => handleSort(col)} className="flex items-center gap-1 py-2 w-full text-left text-gray-300 hover:text-gray-100 transition-colors">
                          {col.charAt(0).toUpperCase() + col.slice(1)}
                          {sortCol === col ? (sortAsc ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />) : <ChevronsUpDown className="w-3 h-3 text-gray-600" />}
                        </button>
                      </th>
                    ))}
                    <th className="text-left px-2 py-0 w-16 bg-gray-900">
                      <button onClick={() => handleSort('priority')} className="flex items-center gap-1 py-2 w-full text-left text-gray-300 hover:text-gray-100 transition-colors">
                        Prio
                        {sortCol === 'priority' ? (sortAsc ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />) : <ChevronsUpDown className="w-3 h-3 text-gray-600" />}
                      </button>
                    </th>
                    <th className="text-left px-2 py-2 w-12 bg-gray-900">Off</th>
                    <th className="text-left px-2 py-2 w-8 bg-gray-900">Cmt</th>
                  </tr>
                  <tr className="bg-gray-900 border-t border-gray-800">
                    <td className="px-1 py-1" />
                    {(['id', 'event', 'from', 'to'] as const).map(col => (
                      <td key={col} className="px-1 py-1">
                        <input value={filters[col]} onChange={e => setFilter(col, e.target.value)} placeholder="filter…"
                          className="w-full bg-gray-800 border border-gray-700 rounded px-1.5 py-0.5 text-xs text-gray-200 placeholder-gray-600 focus:outline-none focus:border-emerald-600" />
                      </td>
                    ))}
                    <td className="px-1 py-1" /><td className="px-1 py-1" /><td className="px-1 py-1" />
                  </tr>
                </thead>
                <tbody>
                  {visibleRows.map(({ r, idx }) => (
                    <tr key={`${r.id}-${idx}`} onClick={() => selectRule(idx)}
                      className={['border-t border-gray-800 cursor-pointer', r.disable ? 'opacity-40' : '',
                        idx === selectedIndex ? 'bg-orange-950/80' : 'bg-gray-950 hover:bg-gray-900/50'].join(' ')}>
                      <td className="px-2 py-1.5 text-gray-500">{idx + 1}</td>
                      <td className="px-2 py-1.5 text-gray-200">{r.id}</td>
                      <td className="px-2 py-1.5 text-gray-300">{r.event}</td>
                      <td className="px-2 py-1.5 text-gray-400">{r.from}</td>
                      <td className="px-2 py-1.5 text-gray-400">{r.to}</td>
                      <td className="px-2 py-1.5 text-gray-400">{r.priority}</td>
                      <td className="px-2 py-1.5 text-center">{r.disable ? <span className="text-orange-400">●</span> : ''}</td>
                      <td className="px-2 py-1.5 text-center">{r.comment ? <span title={r.comment}><MessageSquare className="w-3 h-3 text-sky-400 inline" /></span> : ''}</td>
                    </tr>
                  ))}
                  {visibleRows.length === 0 && (
                    <tr><td colSpan={8} className="px-3 py-3 text-gray-600 text-center">No rules match the current filter.</td></tr>
                  )}
                </tbody>
              </table>
              </div>
            </div>

            <div className="grid grid-cols-1 xl:grid-cols-2 gap-4 min-h-[360px]">

              {/* ── Rule Editor ── */}
              <section className="border border-gray-700 rounded p-3 bg-gray-900/40 space-y-3">
                <div className="flex items-center justify-between">
                  <h3 className="text-sm text-gray-200 font-medium">Rule Editor</h3>
                  <button onClick={() => { setSelectedIndex(null); setForm(EMPTY_RULE); setError(null); setMessage(null) }}
                    className="text-xs px-2 py-1 rounded border border-gray-700 text-gray-300 hover:bg-gray-800">
                    New Empty Rule
                  </button>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  <label className="text-xs text-gray-300">
                    ID
                    <input value={form.id} onChange={e => setField('id', e.target.value)} onFocus={() => setFocusedField('id')}
                      className="mt-1 w-full bg-gray-800 border border-gray-600 rounded px-2 py-1 text-sm text-gray-200" />
                  </label>

                  {/* ── Event combobox ── */}
                  <label className="text-xs text-gray-300">
                    Event
                    <select
                      value={form.event}
                      onChange={e => setField('event', e.target.value)}
                      onFocus={() => setFocusedField('event')}
                      className="mt-1 w-full bg-gray-800 border border-gray-600 rounded px-2 py-1 text-sm text-gray-200 focus:outline-none focus:border-emerald-500"
                    >
                      {form.event && !ALL_EVENT_TYPES.includes(form.event) && (
                        <option value={form.event}>{form.event} (unknown)</option>
                      )}
                      {ALL_EVENT_TYPES.map(et => (
                        <option key={et} value={et}>{et}</option>
                      ))}
                    </select>
                  </label>
                </div>

                <label className="block text-xs text-gray-300">
                  Description
                  <input value={form.description ?? ''} onChange={e => setField('description', e.target.value)} onFocus={() => setFocusedField('description')}
                    className="mt-1 w-full bg-gray-800 border border-gray-600 rounded px-2 py-1 text-sm text-gray-200" />
                </label>

                <label className="block text-xs text-gray-300">
                  Comment
                  <textarea value={form.comment ?? ''} onChange={e => setField('comment', e.target.value)} onFocus={() => setFocusedField('comment')}
                    rows={2} placeholder="Persönliche Notizen zu dieser Regel…"
                    className="mt-1 w-full bg-gray-800 border border-gray-600 rounded px-2 py-1 text-sm text-gray-200 resize-y placeholder-gray-600" />
                </label>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  <label className="text-xs text-gray-300">
                    From
                    <input value={form.from} onChange={e => setField('from', e.target.value)} onFocus={() => setFocusedField('from')}
                      className="mt-1 w-full bg-gray-800 border border-gray-600 rounded px-2 py-1 text-sm text-gray-200" />
                  </label>
                  <label className="text-xs text-gray-300">
                    To
                    <input value={form.to} onChange={e => setField('to', e.target.value)} onFocus={() => setFocusedField('to')}
                      className="mt-1 w-full bg-gray-800 border border-gray-600 rounded px-2 py-1 text-sm text-gray-200" />
                  </label>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-3 pt-2">
                  <div>
                    <div className="flex items-end gap-4">
                      <label className="block text-xs text-gray-300 max-w-[160px]">
                        Priority
                        <input type="number" value={form.priority} onChange={e => setField('priority', Number(e.target.value))} onFocus={() => setFocusedField('priority')}
                          className="mt-1 w-full bg-gray-800 border border-gray-600 rounded px-2 py-1 text-sm text-gray-200" />
                      </label>
                      <label className="flex items-center gap-1.5 text-xs text-gray-300 pb-1 cursor-pointer select-none">
                        <input type="checkbox" checked={form.disable ?? false} onChange={e => setField('disable', e.target.checked)} className="w-3.5 h-3.5 accent-orange-400" />
                        <span className={form.disable ? 'text-orange-400' : ''}>Disable</span>
                      </label>
                    </div>
                    <div className="flex items-center gap-2 pt-2">
                      <button onClick={() => void handleUpdate()} disabled={saving}
                        className="text-xs px-3 py-1.5 rounded bg-emerald-700 hover:bg-emerald-600 text-white disabled:opacity-50 flex items-center gap-1">
                        <Save className="w-3.5 h-3.5" /> Update
                      </button>
                      <button onClick={() => void handleSaveAsNew()} disabled={saving}
                        className="text-xs px-3 py-1.5 rounded bg-blue-700 hover:bg-blue-600 text-white disabled:opacity-50">
                        Save As New
                      </button>
                      <button onClick={() => void handleDelete()} disabled={saving || selectedIndex === null}
                        className="text-xs px-3 py-1.5 rounded bg-red-700 hover:bg-red-600 text-white disabled:opacity-50 flex items-center gap-1">
                        <Trash2 className="w-3.5 h-3.5" /> Delete
                      </button>
                    </div>
                  </div>
                  <div className="border border-gray-700 rounded bg-gray-950/50 p-2">
                    <p className="text-xs text-gray-300 leading-5 whitespace-pre-wrap">{fieldHelp}</p>
                  </div>
                </div>
              </section>

              {/* ── Live Rule Explanation ── */}
              <aside className="border border-gray-700 rounded p-3 bg-gray-900/30 flex flex-col gap-3">
                <h3 className="text-sm text-gray-200 font-medium">Live Rule Explanation</h3>

                {/* Natural language summary */}
                <div className="rounded bg-gray-800/60 px-3 py-2 text-xs text-gray-200 leading-5">
                  {form.event && form.from && form.to ? (
                    <>
                      When <span className="text-emerald-300 font-mono">{form.event}</span> is sent
                      {form.from !== '*'
                        ? <> from <span className="text-sky-300 font-mono">{form.from}</span></>
                        : <> from <span className="text-gray-400">any sender</span></>
                      }, deliver to <span className="text-amber-300 font-mono">{form.to}</span>{' '}
                      with priority <span className="text-purple-300">{form.priority}</span>.
                      {form.disable && <span className="ml-1 text-orange-400">(disabled)</span>}
                    </>
                  ) : (
                    <span className="text-gray-500">Fill in Event, From, and To to see the explanation.</span>
                  )}
                </div>

                {/* Event details */}
                <div className="space-y-1.5 text-xs">
                  <p className="text-gray-500 uppercase tracking-wide text-[10px] font-semibold">Event</p>
                  <div className="grid grid-cols-[80px_1fr] gap-x-2 gap-y-0.5">
                    <span className="text-gray-500">Type</span>
                    <span className="text-emerald-300 font-mono">{form.event || '—'}</span>
                    {eventInfo ? (
                      <>
                        <span className="text-gray-500">What</span>
                        <span className="text-gray-200">{eventInfo.what}</span>
                        <span className="text-gray-500">Sent by</span>
                        <span className="text-sky-300">{eventInfo.generatedBy}</span>
                      </>
                    ) : form.event ? (
                      <>
                        <span className="text-gray-500">What</span>
                        <span className="text-amber-400">Unknown event type — verify spelling</span>
                      </>
                    ) : null}
                  </div>
                </div>

                {/* From / To details */}
                <div className="grid grid-cols-2 gap-3 text-xs">
                  <div className="space-y-1">
                    <p className="text-gray-500 uppercase tracking-wide text-[10px] font-semibold">From</p>
                    <p className="font-mono text-sky-300">{form.from || '—'}</p>
                    <p className="text-gray-400">{classifyFrom(form.from)}</p>
                  </div>
                  <div className="space-y-1">
                    <p className="text-gray-500 uppercase tracking-wide text-[10px] font-semibold">To</p>
                    <p className="font-mono text-amber-300">{form.to || '—'}</p>
                    <p className="text-gray-400">{classifyTarget(form.to)}</p>
                  </div>
                </div>

                {/* Validation */}
                <div className="border-t border-gray-700 pt-2">
                  <p className="text-[10px] text-gray-500 uppercase tracking-wide font-semibold mb-1">Validation</p>
                  {issues.length === 0 ? (
                    <p className="text-xs text-emerald-400">No issues detected.</p>
                  ) : (
                    <ul className="text-xs text-amber-300 space-y-0.5">
                      {issues.map(issue => <li key={issue}>· {issue}</li>)}
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
