/**
 * EntityHistoryModal — shows the last runs/decisions for one config entity.
 *
 * Generic viewer for the "History" button added to the Agent, EventComposer,
 * Snapshot-Profile and Decision-Prompt-Profile editors. Backed by a single
 * GET /entity-history/{entity_type}/{entity_id} endpoint that normalizes
 * ec_runs and agent_decisions into one shape (see api.py get_entity_history).
 *
 * Each entry shows what went IN (the triggering event), what came OUT (the
 * script/agent's own return value), and any side-channel events emitted
 * along the way (e.g. ec_guard_block) that never show up in the return value.
 */
import { useEffect, useState } from 'react'
import { ChevronDown, ChevronRight, Copy, Loader2, RefreshCw, X } from 'lucide-react'
import { api, type EntityHistoryEntry, type EntityHistoryType } from '@/api/client'

interface Props {
  entityType: EntityHistoryType
  entityId: string
  onClose: () => void
}

const ENTITY_TYPE_LABEL: Record<EntityHistoryType, string> = {
  agent: 'Agent',
  event_composer: 'EventComposer',
  snapshot_profile: 'Snapshot Profile',
  decision_prompt_profile: 'Decision Prompt Profile',
}

function fmtJson(value: unknown): string {
  if (value === null || value === undefined) return '(none)'
  try {
    return JSON.stringify(value, null, 2)
  } catch {
    return String(value)
  }
}

function CopyButton({ text }: { text: string }) {
  return (
    <button
      onClick={() => void navigator.clipboard.writeText(text)}
      className="flex items-center gap-1 text-xs text-white hover:text-gray-200 transition-colors"
      title="Copy"
    >
      <Copy className="w-3 h-3" />
      Copy
    </button>
  )
}

function JsonBlock({ label, value }: { label: string; value: unknown }) {
  const text = fmtJson(value)
  return (
    <div>
      <div className="flex items-center justify-between mb-1">
        <span className="text-xs text-white">{label}</span>
        <CopyButton text={text} />
      </div>
      <pre className="text-xs text-gray-300 bg-gray-900 rounded p-3 overflow-auto max-h-64 font-mono whitespace-pre-wrap break-all">
        {text}
      </pre>
    </div>
  )
}

function EntryRow({ entry }: { entry: EntityHistoryEntry }) {
  const [open, setOpen] = useState(false)

  return (
    <div className="border border-gray-700 rounded overflow-hidden">
      <button
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center gap-2 px-3 py-2 bg-gray-900 hover:bg-gray-800/80 transition-colors text-left"
      >
        {open ? <ChevronDown className="w-3.5 h-3.5 text-gray-500 flex-shrink-0" /> : <ChevronRight className="w-3.5 h-3.5 text-gray-500 flex-shrink-0" />}
        <span className={entry.success ? 'text-emerald-400 text-xs flex-shrink-0' : 'text-red-400 text-xs flex-shrink-0'}>
          {entry.success ? '✓' : '✗'}
        </span>
        <span className="text-xs text-gray-300 font-mono truncate">{entry.trigger ?? '(unknown trigger)'}</span>
        {entry.emitted_events.length > 0 && (
          <span className="text-xs text-orange-400 bg-orange-900/20 rounded px-1.5 py-0.5 flex-shrink-0">
            {entry.emitted_events.length} emitted event{entry.emitted_events.length === 1 ? '' : 's'}
          </span>
        )}
        <span className="text-xs text-white flex-shrink-0 ml-auto">
          {entry.latency_ms != null ? `${entry.latency_ms.toFixed(0)} ms` : ''}
        </span>
        <span className="text-xs text-white flex-shrink-0">{entry.timestamp ?? ''}</span>
      </button>

      {open && (
        <div className="p-3 space-y-3 bg-gray-950/60">
          {entry.error && (
            <div className="text-xs text-red-400 bg-red-900/20 rounded p-2 font-mono whitespace-pre-wrap">
              {entry.error}
            </div>
          )}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <JsonBlock label="In (triggering event)" value={entry.input} />
            <JsonBlock label="Out (return value)" value={entry.output} />
          </div>
          {entry.tool_calls && entry.tool_calls.length > 0 && (
            <JsonBlock label="Tool calls" value={entry.tool_calls} />
          )}
          {entry.emitted_events.length > 0 && (
            <div>
              <span className="text-xs text-orange-400 mb-1 block">
                Emitted events (side-channel, not in the return value)
              </span>
              <div className="space-y-2">
                {entry.emitted_events.map(ev => (
                  <div key={ev.id} className="border border-orange-900/40 rounded p-2 bg-orange-950/10">
                    <div className="flex items-center gap-2 text-xs mb-1">
                      <span className="text-orange-300 font-mono">{ev.event_type}</span>
                      <span className="text-gray-600">{ev.created_at}</span>
                    </div>
                    <pre className="text-xs text-gray-300 font-mono whitespace-pre-wrap break-all">
                      {fmtJson(ev.payload)}
                    </pre>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export function EntityHistoryModal({ entityType, entityId, onClose }: Props) {
  const [entries, setEntries] = useState<EntityHistoryEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  function load() {
    setLoading(true)
    setError(null)
    api.getEntityHistory(entityType, entityId, 50)
      .then(setEntries)
      .catch(e => setError(String(e)))
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [entityType, entityId])

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="w-full max-w-4xl max-h-[85vh] flex flex-col bg-gray-950 border border-gray-700 rounded-xl overflow-hidden shadow-2xl">
        <div className="flex items-center justify-between px-4 py-3 bg-gray-900 border-b border-gray-700 flex-shrink-0">
          <span className="text-sm font-semibold text-emerald-400">
            History — {ENTITY_TYPE_LABEL[entityType]} <span className="text-gray-500 font-mono">{entityId}</span>
          </span>
          <div className="flex items-center gap-3">
            <button onClick={load} className="text-gray-500 hover:text-gray-300" title="Refresh">
              <RefreshCw className="w-3.5 h-3.5" />
            </button>
            <button onClick={onClose} className="text-gray-500 hover:text-gray-300">
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        <div className="p-4 overflow-y-auto flex-1 space-y-2">
          {loading && (
            <div className="flex items-center gap-2 text-white text-xs">
              <Loader2 className="w-3.5 h-3.5 animate-spin" /> Loading history…
            </div>
          )}
          {error && (
            <div className="text-xs text-red-400 bg-red-900/20 rounded p-2">{error}</div>
          )}
          {!loading && !error && entries.length === 0 && (
            <div className="text-xs text-white">No runs recorded yet for this entity.</div>
          )}
          {entries.map(entry => <EntryRow key={entry.id} entry={entry} />)}
        </div>
      </div>
    </div>
  )
}
