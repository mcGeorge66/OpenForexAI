/**
 * TraceViewer — visualises the full event chain for a single event.
 *
 * Shows a vertical waterfall timeline of all ancestor events + the
 * target event itself (root first, target last).
 * Clicking an event expands its full payload.
 */
import { useEffect, useState } from 'react'
import { api, type EventLogEntry } from '@/api/client'
import { AlertCircle, ChevronDown, ChevronRight, Download, Loader2, X } from 'lucide-react'

const EVENT_TYPE_COLORS: Record<string, string> = {
  m5_candle_trigger:   'bg-blue-800 text-blue-200',
  m5_candle_update:    'bg-blue-900 text-blue-300',
  ec_output:           'bg-purple-800 text-purple-200',
  ec_guard_block:      'bg-orange-800 text-orange-200',
  signal_generated:    'bg-green-800 text-green-200',
  signal_approved:     'bg-green-700 text-green-200',
  signal_rejected:     'bg-red-800 text-red-200',
  order_request:       'bg-green-800 text-green-200',
  order_result:        'bg-green-700 text-green-200',
  order_placed:        'bg-green-700 text-green-200',
  llm_request:         'bg-indigo-800 text-indigo-200',
  llm_response:        'bg-indigo-700 text-indigo-200',
  repo_request:        'bg-gray-700 text-white',
  repo_response:       'bg-gray-600 text-white',
  candles_request:     'bg-sky-800 text-sky-200',
  candles_response:    'bg-sky-700 text-sky-200',
}

function eventColor(eventType: string): string {
  return EVENT_TYPE_COLORS[eventType] ?? 'bg-gray-700 text-white'
}

function formatTs(ts: string): string {
  try {
    const d = new Date(ts)
    return d.toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit', second: '2-digit', fractionalSecondDigits: 3 })
  } catch {
    return ts
  }
}

function relativeMs(base: string, ts: string): string {
  try {
    const diff = new Date(ts).getTime() - new Date(base).getTime()
    return diff >= 0 ? `+${diff}ms` : `${diff}ms`
  } catch {
    return ''
  }
}

interface Props {
  eventId: string
  onClose?: () => void
  embedded?: boolean  // when true, no close button / backdrop
}

export function TraceViewer({ eventId, onClose, embedded }: Props) {
  const [events, setEvents] = useState<EventLogEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set())

  useEffect(() => {
    // No setLoading(true)/setError(null) reset here: callers key this component by eventId
    // (EventLogView.tsx, Orderbook.tsx) so a new eventId always remounts it fresh — the
    // useState initializers above already start at loading=true/error=null.
    api.getEventTrace(eventId)
      .then(setEvents)
      .catch(e => setError(String(e)))
      .finally(() => setLoading(false))
  }, [eventId])

  const rootTs = events[0]?.created_at ?? ''

  function exportTrace() {
    const root = events[0]
    const filename = root
      ? `trace_${root.event_type}_${root.created_at.replace(/[:.+]/g, '-').slice(0, 19)}.json5`
      : `trace_${eventId.slice(0, 8)}.json5`
    const blob = new Blob(
      [JSON.stringify(events, null, 2)],
      { type: 'application/json' },
    )
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    a.click()
    URL.revokeObjectURL(url)
  }

  function toggle(id: string) {
    setExpandedIds(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const content = (
    <div className={`flex flex-col h-full bg-gray-950 ${embedded ? '' : 'rounded-lg overflow-hidden'}`}>
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-2 bg-gray-900 border-b border-gray-700 flex-shrink-0">
        <div className="flex items-center gap-2">
          <span className="text-xs font-semibold text-emerald-400 uppercase tracking-wider">Event Trace</span>
          {!loading && events.length > 0 && (
            <span className="text-xs text-white">{events.length} event{events.length !== 1 ? 's' : ''}</span>
          )}
        </div>
        <div className="flex items-center gap-2">
          {!loading && events.length > 0 && (
            <button
              onClick={exportTrace}
              className="flex items-center gap-1 px-2 py-1 rounded text-xs text-white hover:text-gray-200 hover:bg-gray-800"
              title="Export trace as JSON5"
            >
              <Download className="w-3 h-3" /> Export
            </button>
          )}
          {onClose && (
            <button onClick={onClose} className="text-gray-500 hover:text-gray-300">
              <X className="w-4 h-4" />
            </button>
          )}
        </div>
      </div>

      {/* Body */}
      <div className="flex-1 overflow-y-auto p-3">
        {loading && (
          <div className="flex items-center gap-2 text-gray-500 text-sm p-4">
            <Loader2 className="w-4 h-4 animate-spin" />
            Loading trace…
          </div>
        )}
        {error && (
          <div className="flex items-center gap-2 text-red-400 text-sm p-4">
            <AlertCircle className="w-4 h-4" />
            {error}
          </div>
        )}
        {!loading && !error && events.length === 0 && (
          <div className="text-gray-500 text-sm p-4">No events found in trace.</div>
        )}

        {!loading && !error && events.map((ev, idx) => {
          const isTarget = ev.id === eventId
          const isExpanded = expandedIds.has(ev.id)
          const isLast = idx === events.length - 1
          const colorCls = eventColor(ev.event_type)

          return (
            <div key={ev.id} className="relative">
              {/* Connector line */}
              {!isLast && (
                <div className="absolute left-[15px] top-[28px] bottom-0 w-px bg-gray-700" />
              )}

              <div className={`relative flex gap-3 mb-1 ${isTarget ? 'opacity-100' : 'opacity-80'}`}>
                {/* Node dot */}
                <div className={`flex-shrink-0 mt-1 w-[10px] h-[10px] rounded-full border-2 ml-[10px] mt-[9px] ${isTarget ? 'border-emerald-400 bg-emerald-800' : 'border-gray-600 bg-gray-800'}`} />

                {/* Card */}
                <div
                  className={`flex-1 rounded border cursor-pointer select-none ${isTarget ? 'border-emerald-700 bg-gray-900' : 'border-gray-700 bg-gray-900 hover:border-gray-600'}`}
                  onClick={() => toggle(ev.id)}
                >
                  <div className="flex items-center gap-2 px-3 py-1.5">
                    <span className={`text-[10px] font-mono px-1.5 py-0.5 rounded ${colorCls}`}>
                      {ev.event_type}
                    </span>
                    <span className="text-xs text-white font-mono">{formatTs(ev.created_at)}</span>
                    {rootTs && ev.created_at !== rootTs && (
                      <span className="text-[10px] text-white font-mono">{relativeMs(rootTs, ev.created_at)}</span>
                    )}
                    {isTarget && <span className="text-[10px] text-emerald-400 ml-auto">← target</span>}
                    <span className="ml-auto text-gray-600">
                      {isExpanded ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
                    </span>
                  </div>

                  <div className="px-3 pb-1 flex items-center gap-3 text-[10px] text-white font-mono">
                    <span>{ev.source_agent}</span>
                    {ev.target_agent && <><span>→</span><span>{ev.target_agent}</span></>}
                    {ev.correlation && <span className="text-gray-700 truncate max-w-[120px]" title={ev.correlation}>corr:{ev.correlation.slice(0, 8)}</span>}
                  </div>

                  {isExpanded && (
                    <div className="px-3 pb-3 border-t border-gray-800 mt-1 pt-2">
                      <div className="text-[10px] text-white font-mono mb-1">id: {ev.id}</div>
                      {ev.chain.length > 0 && (
                        <div className="text-[10px] text-white font-mono mb-1">
                          chain: [{ev.chain.map(c => c.slice(0, 8)).join(', ')}]
                        </div>
                      )}
                      <pre className="text-xs text-gray-300 font-mono bg-gray-800 rounded p-2 overflow-x-auto max-h-60 whitespace-pre-wrap break-all">
                        {JSON.stringify(ev.payload, null, 2)}
                      </pre>
                    </div>
                  )}
                </div>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )

  if (embedded) return content

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="w-full max-w-2xl h-[80vh] shadow-xl">
        {content}
      </div>
    </div>
  )
}
