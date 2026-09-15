import { useEffect, useMemo, useState } from 'react'
import { RefreshCw, Save, Trash2, Plus, Send, Lock, AlertTriangle } from 'lucide-react'
import {
  api,
  type NotificationRule,
  type NotificationsBlock,
  type NotificationPreviewResponse,
} from '@/api/client'
import { useProjectRoot, joinPath } from '@/api/useProjectRoot'

// ── Filter conditions ────────────────────────────────────────────────────────
// The rule engine accepts a bare literal (equality) or exactly one operator per
// field. The editor keeps that shape rather than inventing a friendlier one, so
// what is shown here is what the engine evaluates.
const OPERATORS = [
  { value: 'eq',       label: 'equals',          hint: 'Literal comparison (text, number, true/false)' },
  { value: 'ne',       label: 'not equal',       hint: 'Anything but this value' },
  { value: 'regex',    label: 'matches regex',   hint: 'Python regex, a partial match is enough' },
  { value: 'contains', label: 'contains',        hint: 'Plain substring' },
  { value: 'gte',      label: '>=',              hint: 'Numeric' },
  { value: 'gt',       label: '>',               hint: 'Numeric' },
  { value: 'lte',      label: '<=',              hint: 'Numeric' },
  { value: 'lt',       label: '<',               hint: 'Numeric' },
] as const

type OperatorId = typeof OPERATORS[number]['value']
type FilterRow = { id: string; field: string; op: OperatorId; value: string }
type RuleDraft = {
  event: string
  severity: string
  title: string
  template: string
  filters: FilterRow[]
  dedupBy: string
}

let rowSeq = 0
const newRowId = () => `f${++rowSeq}`

/** "true"/"false"/numbers are meant as such; everything else stays a string. */
function coerce(raw: string): unknown {
  const t = raw.trim()
  if (t === 'true') return true
  if (t === 'false') return false
  if (t === 'null') return null
  if (t !== '' && !Number.isNaN(Number(t))) return Number(t)
  return raw
}

function conditionToRow(field: string, cond: unknown): FilterRow {
  if (cond !== null && typeof cond === 'object' && !Array.isArray(cond)) {
    const entry = Object.entries(cond as Record<string, unknown>)[0]
    const op = entry ? entry[0] : 'eq'
    const val = entry ? entry[1] : ''
    const known = OPERATORS.some(o => o.value === op)
    return { id: newRowId(), field, op: (known ? op : 'eq') as OperatorId, value: String(val ?? '') }
  }
  return { id: newRowId(), field, op: 'eq', value: cond === null ? 'null' : String(cond) }
}

function rowsToOnlyIf(rows: FilterRow[]): Record<string, unknown> | undefined {
  const out: Record<string, unknown> = {}
  for (const r of rows) {
    const field = r.field.trim()
    if (!field) continue
    out[field] = r.op === 'eq' ? coerce(r.value) : { [r.op]: coerce(r.value) }
  }
  return Object.keys(out).length > 0 ? out : undefined
}

function ruleToDraft(event: string, rule: NotificationRule): RuleDraft {
  return {
    event,
    severity: rule.severity ?? 'warning',
    title: rule.title ?? '',
    template: rule.template ?? '',
    filters: Object.entries(rule.only_if ?? {}).map(([f, c]) => conditionToRow(f, c)),
    dedupBy: (rule.dedup_by ?? []).join(', '),
  }
}

function draftToRule(d: RuleDraft): NotificationRule {
  const rule: NotificationRule = {
    severity: d.severity,
    title: d.title,
    template: d.template,
  }
  const onlyIf = rowsToOnlyIf(d.filters)
  if (onlyIf) rule.only_if = onlyIf as NotificationRule['only_if']
  const dedup = d.dedupBy.split(',').map(s => s.trim()).filter(Boolean)
  if (dedup.length > 0) rule.dedup_by = dedup
  return rule
}

const EMPTY_DRAFT: RuleDraft = {
  event: '', severity: 'warning', title: '', template: '', filters: [], dedupBy: '',
}

const SEVERITY_STYLE: Record<string, string> = {
  info:     'bg-sky-900/60 text-sky-200 border-sky-600/40',
  warning:  'bg-amber-900/60 text-amber-200 border-amber-600/40',
  critical: 'bg-red-900/60 text-red-200 border-red-600/40',
}

const DEFAULT_SAMPLE = '{\n  "success": false,\n  "instrument": "EURUSD",\n  "error": "order_send returned None"\n}'

export function TelegramDesigner() {
  const root = useProjectRoot()
  const [block, setBlock] = useState<NotificationsBlock>({})
  const [eventTypes, setEventTypes] = useState<string[]>([])
  const [severities, setSeverities] = useState<string[]>(['info', 'warning', 'critical'])
  const [selected, setSelected] = useState<string | null>(null)
  const [draft, setDraft] = useState<RuleDraft>(EMPTY_DRAFT)
  const [samplePayload, setSamplePayload] = useState(DEFAULT_SAMPLE)
  const [preview, setPreview] = useState<NotificationPreviewResponse | null>(null)
  const [previewError, setPreviewError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [active, setActive] = useState(false)
  const [inactiveReason, setInactiveReason] = useState<string | null>(null)

  const rules = block.rules ?? {}
  const ruleNames = useMemo(() => Object.keys(rules).sort(), [rules])

  const load = async () => {
    setLoading(true); setError(null); setMessage(null)
    try {
      const res = await api.getNotificationsConfig()
      const next = res.notifications ?? {}
      setBlock(next)
      setEventTypes(res.event_types ?? [])
      setActive(res.active)
      setInactiveReason(res.inactive_reason)
      if (res.severities && res.severities.length > 0) setSeverities(res.severities)
      const nextRules = next.rules ?? {}
      const first = Object.keys(nextRules).sort()[0]
      if (first) {
        setSelected(first)
        setDraft(ruleToDraft(first, nextRules[first]))
        void loadRealSample(first, true)
      } else { setSelected(null); setDraft(EMPTY_DRAFT) }
    } catch (err) { setError(String(err)) }
    finally { setLoading(false) }
  }

  useEffect(() => { void load() }, [])

  // Preview runs server-side against the real engine, so it cannot drift from
  // what actually gets sent. Debounced because every keystroke would hit it.
  useEffect(() => {
    if (!draft.event) { setPreview(null); return }
    const handle = setTimeout(() => {
      let payload: Record<string, unknown> = {}
      try {
        payload = samplePayload.trim() ? JSON.parse(samplePayload) as Record<string, unknown> : {}
      } catch (err) {
        setPreviewError(`The example payload is not valid JSON: ${String(err)}`)
        setPreview(null)
        return
      }
      setPreviewError(null)
      api.previewNotificationRule({
        rule: draftToRule(draft),
        event_type: draft.event,
        instrument: String(payload.instrument ?? payload.pair ?? ''),
        payload,
      }).then(setPreview).catch(err => { setPreviewError(String(err)); setPreview(null) })
    }, 350)
    return () => clearTimeout(handle)
  }, [draft, samplePayload])

  const issues = useMemo(() => {
    const out: string[] = []
    if (!draft.event.trim()) out.push('The event type is missing — it decides what the rule reacts to at all.')
    if (!draft.title.trim() && !draft.template.trim()) out.push('Title and text are both empty — the message would be discarded.')
    if (selected === null && draft.event && rules[draft.event]) {
      out.push(`Note: a rule for "${draft.event}" already exists — saving overwrites it.`)
    }
    draft.filters.forEach(f => {
      if (!f.field.trim()) return
      if (['gt', 'gte', 'lt', 'lte'].includes(f.op) && Number.isNaN(Number(f.value.trim()))) {
        out.push(`Filter "${f.field}": ${f.op} needs a number, "${f.value}" is not one.`)
      }
      if (f.op === 'regex') {
        try { new RegExp(f.value) } catch { out.push(`Filter "${f.field}": "${f.value}" is not a valid regex.`) }
      }
    })
    return out
  }, [draft, rules, selected])

  const blocking = issues.filter(i => !i.startsWith('Hinweis:'))

  const persist = async (nextRules: Record<string, NotificationRule>, keep: string | null, okMsg: string) => {
    setSaving(true); setError(null); setMessage(null)
    try {
      const res = await api.saveNotificationsConfig({ ...block, rules: nextRules })
      const saved = res.notifications ?? {}
      setBlock(saved)
      const savedRules = saved.rules ?? {}
      if (keep && savedRules[keep]) { setSelected(keep); setDraft(ruleToDraft(keep, savedRules[keep])) }
      else { setSelected(null); setDraft(EMPTY_DRAFT) }
      setMessage(
        `${okMsg} — ${res.derived_routing_rules} Routing-Regeln abgeglichen` +
        (res.applied_without_restart
          ? ', sofort aktiv ohne Neustart.'
          : '. Service not reachable, becomes active only after a restart.'),
      )
    } catch (err) { setError(String(err)) }
    finally { setSaving(false) }
  }

  const handleSave = async () => {
    if (blocking.length > 0) { setError('Bitte zuerst die Hinweise beheben.'); return }
    const next = { ...rules }
    if (selected && selected !== draft.event) delete next[selected]
    next[draft.event] = draftToRule(draft)
    await persist(next, draft.event, `Regel "${draft.event}" gespeichert`)
  }

  const handleDelete = async () => {
    if (!selected) return
    const next = { ...rules }
    delete next[selected]
    await persist(next, null, `Rule "${selected}" deleted`)
  }

  const handleSettingsSave = () => persist(rules, selected, 'Einstellungen gespeichert')

  /** Pull the newest real event of this type as the sample payload.
   *  A preview against a made-up payload proves nothing; against the last
   *  real one it shows exactly what the next message will look like. */
  const loadRealSample = async (eventType: string, quiet = false): Promise<boolean> => {
    if (!eventType) return false
    try {
      const events = await api.getEvents({ event_type: eventType, limit: 1 })
      const payload = events?.[0]?.payload
      if (!payload || typeof payload !== 'object') {
        if (!quiet) setError(`No stored "${eventType}" event found — please enter an example by hand.`)
        return false
      }
      setSamplePayload(JSON.stringify(payload, null, 2))
      if (!quiet) setMessage(`Letztes echtes "${eventType}"-Event geladen.`)
      return true
    } catch (err) {
      if (!quiet) setError(String(err))
      return false
    }
  }

  const selectRule = (name: string) => {
    setSelected(name)
    setDraft(ruleToDraft(name, rules[name]))
    setError(null); setMessage(null)
    void loadRealSample(name, true)
  }

  /** Sends the channel smoke test — generic text, no rule involved. */
  const sendChannelTest = async () => {
    setError(null); setMessage(null)
    try {
      const res = await api.sendNotificationTest({
        severity: 'info',
        title: 'OpenForexAI Testnachricht',
        text: 'If you can read this, the channel works.',
      })
      setMessage(res.sent ? 'Testnachricht verschickt.' : `Nicht verschickt: ${res.reason ?? 'unbekannt'}`)
    } catch (err) { setError(String(err)) }
  }

  /** Sends exactly what the preview shows, so the phone gets the real thing. */
  const sendRuleTest = async () => {
    setError(null); setMessage(null)
    if (!preview) { setError('No preview — pick an event type and check the example payload.'); return }
    if (!preview.title && !preview.text) {
      setError('Title and text are empty — there would be nothing to send.')
      return
    }
    try {
      const res = await api.sendNotificationTest({
        severity: preview.severity,
        title: preview.title,
        text: preview.text,
      })
      setMessage(res.sent
        ? `Sent to chat ${preview.chat_id ?? '—'}. Check Telegram.`
        : `Nicht verschickt: ${res.reason ?? 'unbekannt'}`)
    } catch (err) { setError(String(err)) }
  }

  const setField = <K extends keyof RuleDraft>(key: K, value: RuleDraft[K]) =>
    setDraft(prev => ({ ...prev, [key]: value }))

  const setFilter = (id: string, patch: Partial<FilterRow>) =>
    setDraft(prev => ({ ...prev, filters: prev.filters.map(f => f.id === id ? { ...f, ...patch } : f) }))

  const inputCls = 'mt-1 w-full bg-gray-800 border border-gray-600 rounded px-2 py-1 text-sm text-gray-200 focus:outline-none focus:border-emerald-500'

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between px-4 py-2 bg-gray-900 border-b border-gray-700 flex-shrink-0">
        <span className="text-sm text-gray-300 font-medium">Telegram Designer</span>
        <div className="flex items-center gap-3">
          <span className="text-xs text-white">
            {root ? joinPath(root, 'config', 'config.json5') : 'config/config.json5'} → notifications
          </span>
          <button onClick={() => void load()} disabled={loading || saving}
            className="flex items-center gap-1 text-xs text-white hover:text-gray-200 disabled:opacity-40">
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} /> Refresh
          </button>
        </div>
      </div>

      <div className="flex-1 min-h-0 p-4 bg-gray-950 overflow-auto flex flex-col gap-4">
        {loading && <p className="text-sm text-gray-500 animate-pulse">Lade Benachrichtigungsregeln…</p>}
        {error && <p className="text-sm text-red-400">Fehler: {error}</p>}
        {message && <p className="text-sm text-emerald-400">{message}</p>}

        {!loading && (
          <>
            {/* Effective state, not the config flag — the two can disagree. */}
            <div className={`rounded border px-3 py-2 text-xs flex items-start gap-2 ${
              active
                ? 'border-emerald-600/40 bg-emerald-950/30 text-emerald-200'
                : 'border-red-600/50 bg-red-950/30 text-red-200'}`}>
              <span className="mt-0.5">{active ? '●' : '▲'}</span>
              <span>
                {active ? (
                  <>Dienst <strong>sendet</strong>{block.dry_run ? ' — but dry run is on, it is only logged' : ''}.</>
                ) : (
                  <>Dienst sendet <strong>nicht</strong>. {inactiveReason}</>
                )}
              </span>
            </div>

            {/* ── Channel settings ── */}
            <section className="border border-gray-700 rounded p-3 bg-gray-900/40">
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-sm text-gray-200 font-medium">Kanal</h3>
                <div className="flex items-center gap-2">
                  <button onClick={() => void sendChannelTest()}
                    title="Sends a generic message to check the channel"
                    className="text-xs px-3 py-1.5 rounded bg-sky-700 hover:bg-sky-600 text-white flex items-center gap-1">
                    <Send className="w-3.5 h-3.5" /> Kanal testen
                  </button>
                  <button onClick={() => void handleSettingsSave()} disabled={saving}
                    className="text-xs px-3 py-1.5 rounded bg-emerald-700 hover:bg-emerald-600 text-white disabled:opacity-50 flex items-center gap-1">
                    <Save className="w-3.5 h-3.5" /> Einstellungen speichern
                  </button>
                </div>
              </div>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <label className="flex items-center gap-2 text-xs text-gray-300 pt-5">
                  <input type="checkbox" checked={block.enable ?? false} className="w-3.5 h-3.5 accent-emerald-500"
                    onChange={e => setBlock(b => ({ ...b, enable: e.target.checked }))} />
                  Aktiv (Konfiguration)
                </label>
                <label className="flex items-center gap-2 text-xs text-gray-300 pt-5">
                  <input type="checkbox" checked={block.dry_run ?? false} className="w-3.5 h-3.5 accent-amber-500"
                    onChange={e => setBlock(b => ({ ...b, dry_run: e.target.checked }))} />
                  Dry-Run (nur loggen)
                </label>
                <label className="text-xs text-gray-300">
                  Dedup-Fenster (s)
                  <input type="number" className={inputCls} value={block.dedup_window_seconds ?? 900}
                    onChange={e => setBlock(b => ({ ...b, dedup_window_seconds: Number(e.target.value) }))} />
                </label>
                <label className="text-xs text-gray-300">
                  Max. pro Stunde
                  <input type="number" className={inputCls} value={block.max_per_hour ?? 20}
                    onChange={e => setBlock(b => ({ ...b, max_per_hour: Number(e.target.value) }))} />
                </label>
              </div>
              <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mt-3">
                <label className="text-xs text-gray-300">
                  Bot-Token
                  <input className={`${inputCls} text-gray-500`} value={block.telegram?.bot_token ?? ''} readOnly
                    title="Never delivered to the browser — change it only through the environment variable" />
                  <span className="mt-1 flex items-center gap-1 text-[10px] text-gray-500">
                    <Lock className="w-2.5 h-2.5" /> nur per Umgebungsvariable
                  </span>
                </label>
                {['default', ...severities].map(sev => (
                  <label key={sev} className="text-xs text-gray-300">
                    Chat-ID {sev}
                    <input className={inputCls} value={block.telegram?.chat_ids?.[sev] ?? ''}
                      onChange={e => setBlock(b => ({
                        ...b,
                        telegram: { ...b.telegram, chat_ids: { ...b.telegram?.chat_ids, [sev]: e.target.value } },
                      }))} />
                  </label>
                ))}
              </div>
            </section>

            <div className="grid grid-cols-1 xl:grid-cols-[260px_1fr] gap-4">
              {/* ── Rule list ── */}
              <section className="border border-gray-700 rounded bg-gray-900/40 overflow-hidden self-start">
                <div className="flex items-center justify-between px-3 py-2 bg-gray-900 border-b border-gray-800">
                  <h3 className="text-sm text-gray-200 font-medium">Regeln</h3>
                  <button onClick={() => { setSelected(null); setDraft(EMPTY_DRAFT); setError(null); setMessage(null) }}
                    className="text-xs px-2 py-1 rounded bg-amber-600 hover:bg-amber-500 text-white flex items-center gap-1">
                    <Plus className="w-3 h-3" /> Neu
                  </button>
                </div>
                <ul className="max-h-[420px] overflow-y-auto">
                  {ruleNames.map(name => (
                    <li key={name}>
                      <button
                        onClick={() => selectRule(name)}
                        className={`w-full text-left px-3 py-2 border-b border-gray-800 text-xs ${
                          name === selected ? 'bg-orange-950/80 text-gray-100' : 'text-gray-300 hover:bg-gray-900/60'}`}>
                        <span className="font-mono">{name}</span>
                        <span className={`ml-2 rounded px-1.5 py-0.5 text-[10px] border ${SEVERITY_STYLE[rules[name].severity ?? 'info'] ?? SEVERITY_STYLE.info}`}>
                          {rules[name].severity ?? 'info'}
                        </span>
                        {rules[name].only_if && (
                          <span className="ml-1 text-[10px] text-gray-500">
                            {Object.keys(rules[name].only_if ?? {}).length} Filter
                          </span>
                        )}
                        {rules[name].origin === 'monitor_filter' && (
                          <span
                            title={`Generated from the monitor filter "${rules[name].source_filter ?? ''}"`}
                            className="ml-1 rounded px-1.5 py-0.5 text-[10px] bg-sky-900/60 text-sky-200 border border-sky-600/40"
                          >
                            Monitor
                          </span>
                        )}
                      </button>
                    </li>
                  ))}
                  {ruleNames.length === 0 && (
                    <li className="px-3 py-3 text-xs text-gray-600">Noch keine Regel.</li>
                  )}
                </ul>
                <p className="px-3 py-2 text-[10px] text-gray-500 border-t border-gray-800 leading-4">
                  Jede Regel erzeugt automatisch ihre Routing-Regel (<span className="font-mono">owner: telegram</span>),
                  sichtbar und gesperrt im Event-Routing-Designer. Nichts doppelt pflegen.
                </p>
              </section>

              {/* ── Rule editor ── */}
              <section className="border border-gray-700 rounded p-3 bg-gray-900/40 space-y-3">
                <div className="flex items-center justify-between">
                  <h3 className="text-sm text-gray-200 font-medium">
                    {selected ? `Regel: ${selected}` : 'Neue Regel'}
                  </h3>
                  <div className="flex items-center gap-2">
                    <button onClick={() => void sendRuleTest()} disabled={!preview?.title && !preview?.text}
                      title="Sends exactly the message from the preview to Telegram"
                      className="text-xs px-3 py-1.5 rounded bg-sky-700 hover:bg-sky-600 text-white disabled:opacity-40 flex items-center gap-1">
                      <Send className="w-3.5 h-3.5" /> An Telegram senden
                    </button>
                    <button onClick={() => void handleSave()} disabled={saving}
                      className="text-xs px-3 py-1.5 rounded bg-emerald-700 hover:bg-emerald-600 text-white disabled:opacity-50 flex items-center gap-1">
                      <Save className="w-3.5 h-3.5" /> Speichern
                    </button>
                    <button onClick={() => void handleDelete()} disabled={saving || !selected}
                      className="text-xs px-3 py-1.5 rounded bg-red-700 hover:bg-red-600 text-white disabled:opacity-50 flex items-center gap-1">
                      <Trash2 className="w-3.5 h-3.5" /> Löschen
                    </button>
                  </div>
                </div>

                {selected && rules[selected]?.origin === 'monitor_filter' && (
                  <div className="rounded border border-sky-600/40 bg-sky-950/30 px-3 py-2 text-xs text-sky-200">
                    Aus dem Monitor-Filter <span className="font-mono">{rules[selected]?.source_filter}</span> erzeugt.
                    Die Bedingungen stammen aus dem Filter und werden beim nächsten Speichern dort überschrieben —
                    Titel, Text und Schweregrad kannst du hier frei ändern, die bleiben erhalten.
                  </div>
                )}

                                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  <label className="text-xs text-gray-300">
                    Event-Typ
                    <input list="ofai-event-types" className={inputCls} value={draft.event}
                      onChange={e => setField('event', e.target.value)}
                      placeholder="z.B. order_result" />
                    <datalist id="ofai-event-types">
                      {eventTypes.map(t => <option key={t} value={t} />)}
                    </datalist>
                  </label>
                  <label className="text-xs text-gray-300">
                    Schweregrad (bestimmt den Ziel-Chat)
                    <select className={inputCls} value={draft.severity} onChange={e => setField('severity', e.target.value)}>
                      {severities.map(s => <option key={s} value={s}>{s}</option>)}
                    </select>
                  </label>
                </div>

                <label className="block text-xs text-gray-300">
                  Titel-Template
                  <input className={inputCls} value={draft.title} onChange={e => setField('title', e.target.value)}
                    placeholder="{instrument}: Order abgelehnt" />
                </label>

                <label className="block text-xs text-gray-300">
                  Text-Template
                  <textarea rows={3} className={`${inputCls} resize-y font-mono`} value={draft.template}
                    onChange={e => setField('template', e.target.value)}
                    placeholder="{error}" />
                </label>

                {/* Placeholders */}
                <div className="rounded border border-gray-700 bg-gray-950/50 p-2">
                  <p className="text-[10px] text-white uppercase tracking-wide font-semibold mb-1">
                    Platzhalter aus der Beispiel-Payload — Klick hängt an den Text an
                  </p>
                  <div className="flex flex-wrap gap-1">
                    {(preview?.fields ?? ['event', 'source', 'instrument']).map(f => (
                      <button key={f} onClick={() => setField('template', `${draft.template}{${f}}`)}
                        className="rounded bg-gray-800 hover:bg-gray-700 border border-gray-700 px-1.5 py-0.5 text-[10px] font-mono text-emerald-300">
                        {'{' + f + '}'}
                      </button>
                    ))}
                  </div>
                  <p className="mt-1 text-[10px] text-gray-500">
                    Verschachtelte Pfade funktionieren: <span className="font-mono">{'{order.signal.pair}'}</span>.
                    Fehlende Felder bleiben leer.
                  </p>
                </div>

                {/* Filters */}
                <div className="rounded border border-gray-700 bg-gray-950/40 p-2 space-y-2">
                  <div className="flex items-center justify-between">
                    <p className="text-[10px] text-white uppercase tracking-wide font-semibold">
                      Filter — alle Bedingungen müssen zutreffen
                    </p>
                    <button
                      onClick={() => setDraft(p => ({ ...p, filters: [...p.filters, { id: newRowId(), field: '', op: 'eq', value: '' }] }))}
                      className="text-[10px] px-2 py-0.5 rounded bg-gray-800 hover:bg-gray-700 border border-gray-700 text-gray-200 flex items-center gap-1">
                      <Plus className="w-3 h-3" /> Bedingung
                    </button>
                  </div>
                  {draft.filters.length === 0 && (
                    <p className="text-[11px] text-gray-500">Ohne Filter meldet jedes Vorkommen dieses Events.</p>
                  )}
                  {draft.filters.map(f => (
                    <div key={f.id} className="grid grid-cols-[1fr_150px_1fr_28px] gap-2 items-center">
                      <input className="bg-gray-800 border border-gray-600 rounded px-2 py-1 text-xs text-gray-200 font-mono"
                        placeholder="Feld, z.B. success oder order.pair"
                        value={f.field} onChange={e => setFilter(f.id, { field: e.target.value })} />
                      <select className="bg-gray-800 border border-gray-600 rounded px-2 py-1 text-xs text-gray-200"
                        value={f.op} onChange={e => setFilter(f.id, { op: e.target.value as OperatorId })}
                        title={OPERATORS.find(o => o.value === f.op)?.hint}>
                        {OPERATORS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
                      </select>
                      <input className="bg-gray-800 border border-gray-600 rounded px-2 py-1 text-xs text-gray-200 font-mono"
                        placeholder="Wert" value={f.value} onChange={e => setFilter(f.id, { value: e.target.value })} />
                      <button onClick={() => setDraft(p => ({ ...p, filters: p.filters.filter(x => x.id !== f.id) }))}
                        className="text-gray-500 hover:text-red-400" title="Bedingung entfernen">
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  ))}
                </div>

                <label className="block text-xs text-gray-300">
                  Dedup-Felder (kommagetrennt)
                  <input className={inputCls} value={draft.dedupBy} onChange={e => setField('dedupBy', e.target.value)}
                    placeholder="instrument, agent_id" />
                  <span className="mt-1 block text-[10px] text-gray-500">
                    Macht den Unterdrückungsschlüssel unterscheidbar — sonst verschluckt eine EURUSD-Meldung
                    eine gleichzeitige USDJPY-Meldung.
                  </span>
                </label>

                {/* Preview */}
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
                  <div className="block text-xs text-gray-300">
                    <div className="flex items-center justify-between">
                      <span>Beispiel-Payload (JSON)</span>
                      <button onClick={() => void loadRealSample(draft.event)} disabled={!draft.event}
                        title="Fetches the most recent real event of this type from the event log"
                        className="text-[10px] px-2 py-0.5 rounded bg-gray-800 hover:bg-gray-700 border border-gray-700 text-gray-200 disabled:opacity-40">
                        Echtes Event laden
                      </button>
                    </div>
                    <textarea rows={7} className={`${inputCls} font-mono resize-y`} value={samplePayload}
                      onChange={e => setSamplePayload(e.target.value)} />
                  </div>
                  <div className="rounded border border-gray-700 bg-gray-950/50 p-2 text-xs">
                    <p className="text-[10px] text-white uppercase tracking-wide font-semibold mb-1">
                      Vorschau (echte Regel-Engine)
                    </p>
                    {previewError && <p className="text-amber-300">{previewError}</p>}
                    {!previewError && preview && (
                      <div className="space-y-1">
                        <p className={preview.matches ? 'text-emerald-400' : 'text-gray-500'}>
                          {preview.matches
                            ? '✓ Filters match — the message would be sent'
                            : '✗ Filters do not match — no message'}
                        </p>
                        <div className="rounded bg-gray-900 border border-gray-700 p-2 whitespace-pre-wrap text-gray-200">
                          <span className="font-semibold">{preview.title || '(kein Titel)'}</span>
                          {preview.text ? `\n${preview.text}` : ''}
                        </div>
                        <p className="text-gray-500">
                          Chat: <span className="font-mono text-gray-400">{preview.chat_id ?? '— no chat ID for this severity'}</span>
                        </p>
                        <p className="text-gray-500">
                          Dedup-Schlüssel: <span className="font-mono text-gray-400">{preview.dedup_key}</span>
                        </p>
                      </div>
                    )}
                    {!previewError && !preview && <p className="text-gray-600">Event-Typ wählen für die Vorschau.</p>}
                  </div>
                </div>

                {issues.length > 0 && (
                  <div className="rounded border border-amber-700/50 bg-amber-950/30 p-2">
                    <p className="flex items-center gap-1 text-[10px] text-amber-300 uppercase tracking-wide font-semibold mb-1">
                      <AlertTriangle className="w-3 h-3" /> Hinweise
                    </p>
                    <ul className="text-xs text-amber-200 space-y-0.5">
                      {issues.map(i => <li key={i}>· {i}</li>)}
                    </ul>
                  </div>
                )}
              </section>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
