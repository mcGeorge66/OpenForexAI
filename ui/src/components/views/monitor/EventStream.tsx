/**
 * EventStream — scrollable live event log, used by all Monitor sub-views.
 *
 * Props:
 *   filter   — if provided, only events with event_type in this set are shown.
 *              If omitted (undefined), all events from the stream are shown.
 *   events   — the full ring buffer from useMonitoringStream (parent controls stream)
 *   connected — WebSocket connection state
 */

import { useEffect, useRef, useState } from 'react'
import type { MonitoringEvent } from '@/api/client'
import { ArrowUp, Trash2, X, Copy } from 'lucide-react'

// ── Event-type colour mapping (mirrors tools/monitor.py _TYPE_COLOUR) ─────────

const EVENT_COLOURS: Record<string, string> = {
  // LLM
  llm_request:          'text-blue-300',
  llm_response:         'text-blue-400',
  llm_error:            'text-red-400',
  // Tools
  tool_call_started:    'text-yellow-300',
  tool_call_completed:  'text-yellow-400',
  tool_call_failed:     'text-red-300',
  // Broker
  broker_connected:     'text-emerald-300',
  broker_disconnected:  'text-orange-400',
  broker_reconnecting:  'text-orange-300',
  broker_error:         'text-red-400',
  // Candle / data
  m5_candle_fetched:    'text-cyan-400',
  m5_candle_queued:     'text-cyan-300',
  candle_gap_detected:  'text-orange-400',
  timeframe_calculated: 'text-cyan-500',
  // Bus / signal
  agent_signal_generated: 'text-purple-300',
  agent_decision_made:  'text-purple-400',
  event_bus_message:    'text-gray-400',
  routing_reloaded:     'text-teal-400',
  // System
  system_error:         'text-red-500',
  system_warning:       'text-orange-300',
  system_info:          'text-gray-300',
}

function eventColour(type: string): string {
  return EVENT_COLOURS[type] ?? 'text-gray-400'
}

function formatTs(iso: string): string {
  try {
    return new Date(iso).toISOString().replace('T', ' ').substring(11, 23)
  } catch {
    return iso
  }
}

function formatPayload(eventType: string, payload: Record<string, unknown>): string {
  // For LLM events, show a compact human-readable summary instead of raw JSON
  if (eventType === 'llm_request') {
    const turn = payload.turn !== undefined ? `turn=${payload.turn}` : ''
    const msgs = payload.message_count !== undefined ? `msgs=${payload.message_count}` : ''
    const tools = payload.tool_count !== undefined ? `tools=${payload.tool_count}` : ''
    const names = Array.isArray(payload.tool_names) ? payload.tool_names.slice(0, 4).join(', ') : ''
    const omitted = payload.messages_omitted ? ` (+${payload.messages_omitted} hidden)` : ''
    return [turn, msgs, tools, names ? `[${names}]` : '', omitted].filter(Boolean).join('  ')
  }
  if (eventType === 'llm_response') {
    const turn = payload.turn !== undefined ? `turn=${payload.turn}` : ''
    const reason = payload.stop_reason ? `stop=${payload.stop_reason}` : ''
    const tokens = (payload.input_tokens && payload.output_tokens)
      ? `tokens=${payload.input_tokens}→${payload.output_tokens}` : ''
    const calls = payload.tool_calls ? `tool_calls=${payload.tool_calls}` : ''
    const model = typeof payload.model === 'string' ? payload.model.split('-').slice(0, 2).join('-') : ''
    return [turn, reason, tokens, calls, model].filter(Boolean).join('  ')
  }
  // Replace escaped quotes from embedded JSON strings (e.g. "{\"key\":\"val\"}") → readable
  const s = JSON.stringify(payload).replace(/\\"/g, '"')
  return s.length > 200 ? s.substring(0, 200) + '…' : s
}

// ── Event detail window (draggable + resizable) ───────────────────────────────

interface DetailWindowProps {
  event: MonitoringEvent
  onClose: () => void
}

function EventDetailWindow({ event, onClose }: DetailWindowProps) {
  // Only x/y in state — width/height are set once via DOM ref and then owned
  // entirely by the browser's native CSS resize. If we put w/h in React state
  // and sync via ResizeObserver we get a feedback loop that auto-resizes the window.
  const [pos, setPos] = useState(() => {
    const w = Math.min(640, window.innerWidth - 40)
    const h = Math.min(480, window.innerHeight - 40)
    return {
      x: Math.round((window.innerWidth - w) / 2),
      y: Math.round((window.innerHeight - h) / 2),
    }
  })

  const containerRef = useRef<HTMLDivElement>(null)
  const dragging = useRef(false)
  const dragOrigin = useRef({ mx: 0, my: 0, x: 0, y: 0 })

  // Set initial size once via DOM — React's style prop only controls left/top,
  // so re-renders from drag updates never reset the browser-managed size.
  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    el.style.width  = `${Math.min(640, window.innerWidth  - 40)}px`
    el.style.height = `${Math.min(480, window.innerHeight - 40)}px`
  }, [])

  // Close on Escape
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  // Global mouse-move / mouse-up for drag
  useEffect(() => {
    const onMove = (e: MouseEvent) => {
      if (!dragging.current) return
      const { mx, my, x, y } = dragOrigin.current
      setPos({
        x: Math.max(0, x + e.clientX - mx),
        y: Math.max(0, y + e.clientY - my),
      })
    }
    const onUp = () => { dragging.current = false }
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
    return () => {
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
    }
  }, [])

  const startDrag = (e: React.MouseEvent) => {
    dragOrigin.current = { mx: e.clientX, my: e.clientY, x: pos.x, y: pos.y }
    dragging.current = true
    e.preventDefault()
  }

  // JSON.stringify escapes real newlines as \n and embedded JSON quotes as \".
  // Replace both so the payload is as readable as possible in the detail window.
  const jsonText = JSON.stringify(event.payload, null, 2)
    .replace(/\\n/g, '\n')
    .replace(/\\"/g, '"')

  const copyPayload = async () => {
    try {
      await navigator.clipboard.writeText(jsonText)
    } catch {
      // Ignore clipboard errors silently.
    }
  }

  return (
    <div
      ref={containerRef}
      style={{
        position: 'fixed',
        left: pos.x,
        top: pos.y,
        minWidth: 360,
        minHeight: 200,
        resize: 'both',
        overflow: 'hidden',
        zIndex: 9999,
      }}
      className="flex flex-col bg-gray-900 border border-gray-600 rounded-lg shadow-2xl"
    >
      {/* Title bar — drag handle */}
      <div
        onMouseDown={startDrag}
        className="flex items-center justify-between px-3 py-2 bg-gray-800 border-b border-gray-600 rounded-t-lg cursor-move select-none flex-shrink-0"
      >
        <div className="flex items-center gap-2 text-xs min-w-0">
          <span className={`flex-shrink-0 font-semibold ${eventColour(event.event_type)}`}>
            {event.event_type}
          </span>
          <span className="text-gray-500 flex-shrink-0">·</span>
          <span className="text-gray-400 flex-shrink-0">{formatTs(event.timestamp)}</span>
          {event.broker && (
            <>
              <span className="text-gray-500 flex-shrink-0">·</span>
              <span className="text-gray-500 truncate">
                {event.broker}{event.pair ? `·${event.pair}` : ''}
              </span>
            </>
          )}
        </div>
        <div className="flex items-center gap-1 ml-2">
          <button
            onMouseDown={e => e.stopPropagation()}
            onClick={() => void copyPayload()}
            className="flex-shrink-0 text-gray-500 hover:text-gray-200 transition-colors"
            title="Copy payload"
          >
            <Copy className="w-4 h-4" />
          </button>
          <button
            onMouseDown={e => e.stopPropagation()}
            onClick={onClose}
            className="flex-shrink-0 text-gray-500 hover:text-white transition-colors"
            title="Close (Esc)"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Payload content */}
      <div className="flex-1 overflow-auto p-3 font-mono text-xs text-gray-300 bg-gray-950">
        <pre className="whitespace-pre-wrap break-all leading-relaxed">
          {jsonText}
        </pre>
      </div>

      {/* Resize hint */}
      <div className="flex-shrink-0 flex justify-end px-2 py-0.5 bg-gray-900 border-t border-gray-800 rounded-b-lg">
        <span className="text-gray-700 text-xs select-none">⇲</span>
      </div>
    </div>
  )
}

// ── EventStream ───────────────────────────────────────────────────────────────

interface EventStreamProps {
  events: MonitoringEvent[]
  connected: boolean
  filter?: string[]
  onClear: () => void
}

export function EventStream({ events, connected, filter, onClear }: EventStreamProps) {
  const [autoScroll, setAutoScroll] = useState(true)
  const [detailEvent, setDetailEvent] = useState<MonitoringEvent | null>(null)
  const topRef = useRef<HTMLDivElement>(null)
  const scrollRef = useRef<HTMLDivElement>(null)

  // Apply local filter and reverse so newest events appear at the top
  const filtered = filter && filter.length > 0
    ? events.filter(e => filter.includes(e.event_type))
    : events
  const visible = [...filtered].reverse()

  // Auto-scroll to TOP when new events arrive (newest is displayed at top)
  useEffect(() => {
    if (autoScroll && topRef.current) {
      topRef.current.scrollIntoView({ behavior: 'instant' })
    }
  }, [visible.length, autoScroll])

  const handleScroll = () => {
    const el = scrollRef.current
    if (!el) return
    // Re-enable auto-scroll when user scrolls back to the top
    const atTop = el.scrollTop <= 40
    setAutoScroll(atTop)
  }

  return (
    <div className="flex flex-col h-full">
      {/* Toolbar */}
      <div className="flex items-center justify-between px-3 py-1.5 bg-gray-900 border-b border-gray-700 flex-shrink-0">
        <div className="flex items-center gap-2 text-xs text-gray-500">
          <span className={connected ? 'text-emerald-400' : 'text-red-400'}>
            {connected ? '● Live' : '○ Disconnected'}
          </span>
          <span>·</span>
          <span>{visible.length} events</span>
          {filter && filter.length > 0 && (
            <span className="text-gray-600">
              (filter: {filter.join(', ')})
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setAutoScroll(v => !v)}
            title={autoScroll ? 'Pause auto-scroll' : 'Resume auto-scroll (scroll to top)'}
            className={[
              'flex items-center gap-1 text-xs px-2 py-0.5 rounded transition-colors',
              autoScroll
                ? 'bg-emerald-900/40 text-emerald-300'
                : 'bg-gray-800 text-gray-400 hover:text-gray-200',
            ].join(' ')}
          >
            <ArrowUp className="w-3 h-3" />
            {autoScroll ? 'Auto' : 'Paused'}
          </button>
          <button
            onClick={onClear}
            title="Clear events"
            className="flex items-center gap-1 text-xs px-2 py-0.5 rounded bg-gray-800 text-gray-400 hover:text-red-300 transition-colors"
          >
            <Trash2 className="w-3 h-3" />
            Clear
          </button>
        </div>
      </div>

      {/* Event list */}
      <div
        ref={scrollRef}
        onScroll={handleScroll}
        className="flex-1 overflow-y-auto font-mono text-xs bg-gray-950 p-2 space-y-0.5"
      >
        {/* Sentinel at the TOP — auto-scroll jumps here when new events arrive */}
        <div ref={topRef} />
        {visible.length === 0 && (
          <div className="text-gray-600 text-center py-8">
            {connected ? 'Waiting for events…' : 'Not connected — check backend'}
          </div>
        )}
        {visible.map(evt => (
          <div
            key={evt.id}
            onDoubleClick={() => setDetailEvent(evt)}
            className="flex gap-2 hover:bg-gray-900/50 px-1 py-0.5 rounded cursor-pointer select-none"
            title="Double-click to inspect"
          >
            <span className="text-gray-600 flex-shrink-0 w-20">{formatTs(evt.timestamp)}</span>
            <span className={`flex-shrink-0 w-36 truncate ${eventColour(evt.event_type)}`}>
              {evt.event_type}
            </span>
            {evt.broker && (
              <span className="text-gray-500 flex-shrink-0">[{evt.broker}{evt.pair ? `·${evt.pair}` : ''}]</span>
            )}
            <span className="text-gray-400 truncate">
              {formatPayload(evt.event_type, evt.payload)}
            </span>
          </div>
        ))}
      </div>

      {/* Detail window — rendered outside the scroll container so it floats freely */}
      {detailEvent && (
        <EventDetailWindow
          event={detailEvent}
          onClose={() => setDetailEvent(null)}
        />
      )}
    </div>
  )
}

