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
import { ArrowDown, Trash2 } from 'lucide-react'

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
  const s = JSON.stringify(payload)
  return s.length > 200 ? s.substring(0, 200) + '…' : s
}

interface EventStreamProps {
  events: MonitoringEvent[]
  connected: boolean
  filter?: string[]
  onClear: () => void
}

export function EventStream({ events, connected, filter, onClear }: EventStreamProps) {
  const [autoScroll, setAutoScroll] = useState(true)
  const bottomRef = useRef<HTMLDivElement>(null)
  const scrollRef = useRef<HTMLDivElement>(null)

  // Apply local filter if specified
  const visible = filter && filter.length > 0
    ? events.filter(e => filter.includes(e.event_type))
    : events

  // Auto-scroll to bottom when new events arrive
  useEffect(() => {
    if (autoScroll && bottomRef.current) {
      bottomRef.current.scrollIntoView({ behavior: 'instant' })
    }
  }, [visible.length, autoScroll])

  const handleScroll = () => {
    const el = scrollRef.current
    if (!el) return
    const atBottom = el.scrollTop + el.clientHeight >= el.scrollHeight - 40
    setAutoScroll(atBottom)
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
            title={autoScroll ? 'Pause auto-scroll' : 'Resume auto-scroll'}
            className={[
              'flex items-center gap-1 text-xs px-2 py-0.5 rounded transition-colors',
              autoScroll
                ? 'bg-emerald-900/40 text-emerald-300'
                : 'bg-gray-800 text-gray-400 hover:text-gray-200',
            ].join(' ')}
          >
            <ArrowDown className="w-3 h-3" />
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
        {visible.length === 0 && (
          <div className="text-gray-600 text-center py-8">
            {connected ? 'Waiting for events…' : 'Not connected — check backend'}
          </div>
        )}
        {visible.map(evt => (
          <div key={evt.id} className="flex gap-2 hover:bg-gray-900/50 px-1 py-0.5 rounded">
            <span className="text-gray-600 flex-shrink-0 w-20">{formatTs(evt.timestamp)}</span>
            <span className={`flex-shrink-0 w-36 truncate ${eventColour(evt.event_type)}`}>
              {evt.event_type}
            </span>
            {evt.broker && (
              <span className="text-gray-500 flex-shrink-0">[{evt.broker}{evt.pair ? `·${evt.pair}` : ''}]</span>
            )}
            <span className="text-gray-400 truncate" title={JSON.stringify(evt.payload)}>
              {formatPayload(evt.event_type, evt.payload)}
            </span>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>
    </div>
  )
}
