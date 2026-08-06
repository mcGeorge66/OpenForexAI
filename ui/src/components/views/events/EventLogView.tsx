import { useCallback, useEffect, useState } from 'react'
import { api, type EventLogEntry, type EventLogParams } from '@/api/client'
import { AlertCircle, GitBranch, Layers, Loader2, RefreshCcw, Search, X } from 'lucide-react'
import { TraceViewer } from './TraceViewer'

const EVENT_TYPE_COLORS: Record<string, string> = {
  m5_candle_trigger:    'text-blue-400',
  timer:                'text-blue-500',
  candle_gap_detected:  'text-yellow-400',
  ec_output:            'text-purple-400',
  ec_guard_block:       'text-orange-400',
  signal_generated:     'text-green-400',
  signal_approved:      'text-green-300',
  signal_rejected:      'text-red-400',
  order_request:        'text-emerald-400',
  order_result:         'text-emerald-300',
  order_placed:         'text-emerald-300',
  position_close_request: 'text-amber-400',
  position_close_result:  'text-amber-300',
  risk_breach:          'text-red-500',
  order_book_sync_discrepancy: 'text-yellow-500',
  agent_query:          'text-indigo-400',
  optimization_complete: 'text-cyan-400',
  repo_request:         'text-gray-600',
  repo_response:        'text-gray-600',
  account_status_updated: 'text-gray-600',
}

function eventColor(t: string): string {
  return EVENT_TYPE_COLORS[t] ?? 'text-gray-400'
}

function formatTs(ts: string): string {
  // DB stores timestamps already in the system-configured timezone (ui_utc).
  // Strip the offset and display the wall-clock time as-is.
  try {
    const bare = ts.replace(/([+-]\d{2}:\d{2}|Z)$/, '')
    const d = new Date(bare)
    return d.toLocaleString('de-DE', {
      day: '2-digit', month: '2-digit', year: '2-digit',
      hour: '2-digit', minute: '2-digit', second: '2-digit',
    })
  } catch {
    return ts
  }
}


const DEFAULT_LIMIT = 50

export function EventLogView() {
  const [rootsOnly, setRootsOnly] = useState(true)
  const [filterEventType, setFilterEventType] = useState('')
  const [filterSource, setFilterSource] = useState('')
  const [filterCorrelation, setFilterCorrelation] = useState('')
  const [filterFromTime, setFilterFromTime] = useState('')
  const [filterToTime, setFilterToTime] = useState('')
  const [chainMin, setChainMin] = useState('')
  const [chainMax, setChainMax] = useState('')

  const [events, setEvents] = useState<EventLogEntry[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [traceId, setTraceId] = useState<string | null>(null)
  const [offset, setOffset] = useState(0)
  const [hasMore, setHasMore] = useState(false)

  const load = useCallback(async (newOffset = 0) => {
    setLoading(true)
    setError(null)
    const parsedChainMin = chainMin.trim() ? parseInt(chainMin, 10) : undefined
    const parsedChainMax = chainMax.trim() ? parseInt(chainMax, 10) : undefined
    const p: EventLogParams = {
      limit: DEFAULT_LIMIT,
      offset: newOffset,
      trace_roots_only: rootsOnly,
      ...(filterEventType.trim() ? { event_type: filterEventType.trim() } : {}),
      ...(filterSource.trim() ? { source_agent: filterSource.trim() } : {}),
      ...(filterCorrelation.trim() ? { correlation: filterCorrelation.trim() } : {}),
      ...(filterFromTime.trim() ? { from_time: filterFromTime.trim() } : {}),
      ...(filterToTime.trim() ? { to_time: filterToTime.trim() } : {}),
      ...(parsedChainMin !== undefined && !isNaN(parsedChainMin) ? { chain_min: parsedChainMin } : {}),
      ...(parsedChainMax !== undefined && !isNaN(parsedChainMax) ? { chain_max: parsedChainMax } : {}),
    }
    try {
      const result = await api.getEvents(p)
      if (newOffset === 0) {
        setEvents(result)
      } else {
        setEvents(prev => [...prev, ...result])
      }
      setHasMore(result.length === DEFAULT_LIMIT)
      setOffset(newOffset + result.length)
    } catch (e) {
      setError(String(e))
    } finally {
      setLoading(false)
    }
  }, [rootsOnly, filterEventType, filterSource, filterCorrelation, filterFromTime, filterToTime, chainMin, chainMax])

  useEffect(() => {
    void load(0)
  }, [load])

  function handleSearch(e: React.FormEvent) {
    e.preventDefault()
    void load(0)
  }

  function clearFilters() {
    setFilterEventType('')
    setFilterSource('')
    setFilterCorrelation('')
    setFilterFromTime('')
    setFilterToTime('')
    setChainMin('')
    setChainMax('')
  }

  return (
    <div className="flex flex-col h-full bg-gray-950 text-gray-200">
      {/* Header */}
      <div className="flex items-center gap-3 px-4 py-2 bg-gray-900 border-b border-gray-700 flex-shrink-0">
        <span className="text-sm font-semibold text-emerald-400">Event Log</span>
        {!loading && <span className="text-xs text-white">{events.length} loaded</span>}

        {/* Roots / All toggle */}
        <div className="flex items-center gap-1 ml-2 bg-gray-800 rounded p-0.5">
          <button
            onClick={() => setRootsOnly(true)}
            className={`flex items-center gap-1 px-2 py-1 rounded text-xs transition-colors ${rootsOnly ? 'bg-emerald-700 text-white' : 'text-white hover:text-gray-200'}`}
            title="Show only trace-root events (m5_candle_trigger, order_request, …)"
          >
            <GitBranch className="w-3 h-3" /> Roots
          </button>
          <button
            onClick={() => setRootsOnly(false)}
            className={`flex items-center gap-1 px-2 py-1 rounded text-xs transition-colors ${!rootsOnly ? 'bg-gray-600 text-white' : 'text-white hover:text-gray-200'}`}
            title="Show all persisted events"
          >
            <Layers className="w-3 h-3" /> All
          </button>
        </div>

        <button
          onClick={() => void load(0)}
          className="ml-auto p-1.5 rounded text-gray-500 hover:text-gray-300 hover:bg-gray-800"
          title="Refresh"
        >
          <RefreshCcw className="w-4 h-4" />
        </button>
      </div>

      {/* Filter bar */}
      <form onSubmit={handleSearch} className="flex flex-wrap items-center gap-2 px-4 py-2 bg-gray-900 border-b border-gray-700 flex-shrink-0">
        <input
          type="text"
          placeholder="event_type"
          value={filterEventType}
          onChange={e => setFilterEventType(e.target.value)}
          className="bg-gray-800 border border-gray-700 rounded px-2 py-1 text-xs text-gray-200 placeholder-gray-600 focus:outline-none focus:border-emerald-600 w-36"
        />
        <input
          type="text"
          placeholder="source agent"
          value={filterSource}
          onChange={e => setFilterSource(e.target.value)}
          className="bg-gray-800 border border-gray-700 rounded px-2 py-1 text-xs text-gray-200 placeholder-gray-600 focus:outline-none focus:border-emerald-600 w-40"
        />
        <input
          type="text"
          placeholder="correlation id"
          value={filterCorrelation}
          onChange={e => setFilterCorrelation(e.target.value)}
          className="bg-gray-800 border border-gray-700 rounded px-2 py-1 text-xs text-gray-200 placeholder-gray-600 focus:outline-none focus:border-emerald-600 w-44"
        />
        <input
          type="datetime-local"
          value={filterFromTime}
          onChange={e => setFilterFromTime(e.target.value)}
          className="bg-gray-800 border border-gray-700 rounded px-2 py-1 text-xs text-gray-200 focus:outline-none focus:border-emerald-600"
          title="From time"
        />
        <input
          type="datetime-local"
          value={filterToTime}
          onChange={e => setFilterToTime(e.target.value)}
          className="bg-gray-800 border border-gray-700 rounded px-2 py-1 text-xs text-gray-200 focus:outline-none focus:border-emerald-600"
          title="To time"
        />
        <div className="flex items-center gap-1">
          <input
            type="number"
            min={0}
            value={chainMin}
            onChange={e => setChainMin(e.target.value)}
            placeholder="min"
            className="bg-gray-800 border border-gray-700 rounded px-2 py-1 text-xs text-gray-200 placeholder-gray-600 focus:outline-none focus:border-emerald-600 w-14 text-center"
            title="Min events in chain"
          />
          <span className="text-white text-xs">–</span>
          <input
            type="number"
            min={0}
            value={chainMax}
            onChange={e => setChainMax(e.target.value)}
            placeholder="max"
            className="bg-gray-800 border border-gray-700 rounded px-2 py-1 text-xs text-gray-200 placeholder-gray-600 focus:outline-none focus:border-emerald-600 w-14 text-center"
            title="Max events in chain"
          />
        </div>
        <button type="submit" className="flex items-center gap-1 px-3 py-1 rounded bg-emerald-700 hover:bg-emerald-600 text-white text-xs">
          <Search className="w-3 h-3" /> Search
        </button>
        <button type="button" onClick={clearFilters} className="flex items-center gap-1 px-2 py-1 rounded bg-gray-700 hover:bg-gray-600 text-gray-300 text-xs">
          <X className="w-3 h-3" /> Clear
        </button>
      </form>

      {/* Main content */}
      <div className="flex flex-1 overflow-hidden">
        {/* Table */}
        <div className={`flex flex-col overflow-hidden ${traceId ? 'w-1/2' : 'w-full'}`}>
          {error && (
            <div className="flex items-center gap-2 text-red-400 text-sm px-4 py-3">
              <AlertCircle className="w-4 h-4" /> {error}
            </div>
          )}
          {loading && events.length === 0 && (
            <div className="flex items-center gap-2 text-gray-500 text-sm px-4 py-3">
              <Loader2 className="w-4 h-4 animate-spin" /> Loading…
            </div>
          )}

          <div className="flex-1 overflow-y-auto">
            <table className="w-full text-xs font-mono">
              <thead className="bg-gray-900 sticky top-0 z-10">
                <tr className="text-gray-500 text-left">
                  <th className="px-3 py-1.5 font-normal">Time</th>
                  <th className="px-3 py-1.5 font-normal">Event Type</th>
                  <th className="px-3 py-1.5 font-normal">Source</th>
                  <th className="px-3 py-1.5 font-normal" title={rootsOnly ? 'Total descendant events in this trace' : 'Ancestors / Descendants'}>
                    {rootsOnly ? 'Events' : 'Chain'}
                  </th>
                  <th className="px-3 py-1.5 font-normal">Trace</th>
                </tr>
              </thead>
              <tbody>
                {events.map(ev => (
                  <tr
                    key={ev.id}
                    className={`border-t border-gray-800 hover:bg-gray-900 cursor-pointer ${traceId === ev.id ? 'bg-gray-800' : ''}`}
                    onClick={() => setTraceId(ev.id === traceId ? null : ev.id)}
                  >
                    <td className="px-3 py-1 text-gray-500 whitespace-nowrap">{formatTs(ev.created_at)}</td>
                    <td className={`px-3 py-1 whitespace-nowrap font-semibold ${eventColor(ev.event_type)}`}>{ev.event_type}</td>
                    <td className="px-3 py-1 text-gray-500 truncate max-w-[180px]" title={ev.source_agent}>{ev.source_agent}</td>
                    <td className="px-3 py-1 text-gray-500">
                      {rootsOnly
                        ? (ev.descendant_count > 0 ? `+${ev.descendant_count}` : '—')
                        : `${ev.chain.length > 0 ? `↑${ev.chain.length}` : ''}${ev.descendant_count > 0 ? ` ↓${ev.descendant_count}` : ''}` || '—'
                      }
                    </td>
                    <td className="px-3 py-1">
                      <button
                        onClick={e => { e.stopPropagation(); setTraceId(ev.id === traceId ? null : ev.id) }}
                        className="flex items-center gap-1 text-emerald-600 hover:text-emerald-400"
                        title="Show trace"
                      >
                        <GitBranch className="w-3 h-3" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>

            {hasMore && (
              <div className="px-4 py-3 border-t border-gray-800">
                <button
                  onClick={() => void load(offset)}
                  disabled={loading}
                  className="text-xs text-emerald-500 hover:text-emerald-400 disabled:opacity-50"
                >
                  {loading ? 'Loading…' : 'Load more'}
                </button>
              </div>
            )}
          </div>
        </div>

        {/* Trace panel */}
        {traceId && (
          <div className="w-1/2 border-l border-gray-700 overflow-hidden flex flex-col">
            <TraceViewer
              key={traceId}
              eventId={traceId}
              onClose={() => setTraceId(null)}
              embedded
            />
          </div>
        )}
      </div>
    </div>
  )
}
