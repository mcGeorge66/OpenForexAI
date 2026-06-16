/**
 * EventStream — scrollable live event log, used by all Monitor sub-views.
 *
 * Props:
 *   filter   — if provided, only events with event_type in this set are shown.
 *              If omitted (undefined), all events from the stream are shown.
 *   events   — the full ring buffer from useMonitoringStream (parent controls stream)
 *   connected — WebSocket connection state
 */

import { useEffect, useMemo, useRef, useState } from 'react'
import { api, type MonitoringEvent, type PinnedMonitoringEvent } from '@/api/client'
import { ArrowUp, Pin, PinOff, Trash2, X, Copy } from 'lucide-react'
import { formatTs as formatTsCentral } from '@/utils/time'
import {
  FILTER_FIELDS,
  FILTER_OPERATORS,
  cloneFilterGroup,
  createFilterGroup,
  createFilterRule,
  isPrimaryEvent,
  matchesFilterGroup,
  type MonitorFilterField,
  type MonitorFilterGroup,
  type MonitorFilterJoin,
  type MonitorFilterOperator,
  type SavedMonitorFilter,
} from './filtering'

// ── Event-type colour mapping (mirrors tools/monitor.py _TYPE_COLOUR) ─────────

const EVENT_COLOURS: Record<string, string> = {
  // LLM
  llm_request:                   'text-blue-300',
  llm_response:                  'text-blue-400',
  llm_error:                     'text-red-400',
  llm_turn_started:              'text-blue-200',
  llm_turn_completed:            'text-blue-300',
  llm_turn_failed:               'text-red-300',
  llm_http_attempt_started:      'text-blue-500',
  llm_http_attempt_completed:    'text-blue-400',
  llm_http_attempt_failed:       'text-red-400',
  // Tools
  tool_call_started:             'text-yellow-300',
  tool_call_completed:           'text-yellow-400',
  tool_call_failed:              'text-red-300',
  agent_tool_called:             'text-yellow-200',
  agent_tool_result:             'text-yellow-500',
  // Broker
  broker_connected:              'text-emerald-300',
  broker_disconnected:           'text-orange-400',
  broker_reconnecting:           'text-orange-300',
  broker_error:                  'text-red-400',
  broker_http_request:           'text-emerald-400',
  broker_http_response:          'text-emerald-500',
  // Candle / data
  m5_candle_fetched:             'text-cyan-400',
  m5_candle_queued:              'text-cyan-300',
  candle_gap_detected:           'text-orange-400',
  timeframe_calculated:          'text-cyan-500',
  // Trigger lifecycle
  agent_trigger_received:        'text-gray-400',
  agent_trigger_skipped:         'text-orange-300',
  agent_backlog_detected:        'text-orange-400',
  // Bus / signal
  agent_signal_generated:        'text-purple-300',
  agent_decision_made:           'text-purple-400',
  agent_input_built:             'text-fuchsia-300',
  agent_decision_snapshot_built:   'text-sky-300',
  agent_decision_snapshot_invalid: 'text-red-300',
  event_bus_message:             'text-gray-400',
  routing_reloaded:              'text-teal-400',
  // System
  system_error:                  'text-red-500',
  system_warning:                'text-orange-300',
  system_info:                   'text-gray-300',
}

const RULE_JOIN_OPTIONS: Array<{ value: MonitorFilterJoin; label: string }> = [
  { value: 'START', label: 'Start' },
  { value: 'OR', label: 'OR' },
  { value: 'OR_NOT', label: 'OR NOT' },
  { value: 'AND', label: 'AND' },
  { value: 'AND_NOT', label: 'AND NOT' },
]

function eventColour(type: string): string {
  return EVENT_COLOURS[type] ?? 'text-gray-400'
}

function formatTs(iso: string): string {
  try {
    return formatTsCentral(iso, false)
  } catch {
    return iso
  }
}

function nestedPayload(payload: Record<string, unknown>): Record<string, unknown> | null {
  const inner = payload.payload
  if (!inner || typeof inner !== 'object' || Array.isArray(inner)) return null
  return inner as Record<string, unknown>
}

function llmPayload(payload: Record<string, unknown>): Record<string, unknown> {
  return nestedPayload(payload) ?? payload
}

function llmOrigin(event: MonitoringEvent): 'bus' | 'agent' | null {
  if (event.event_type !== 'llm_request' && event.event_type !== 'llm_response') return null
  if (event.source === 'eventbus') return 'bus'
  if (event.source?.startsWith('agent:')) return 'agent'
  return nestedPayload(event.payload) ? 'bus' : 'agent'
}

function formatPayload(eventType: string, payload: Record<string, unknown>): string {
  // For LLM events, show a compact human-readable summary instead of raw JSON
  if (eventType === 'llm_request') {
    const display = llmPayload(payload)
    const turn = display.turn !== undefined ? `turn=${display.turn}` : ''
    const msgs = display.message_count !== undefined ? `msgs=${display.message_count}` : ''
    const tools = display.tool_count !== undefined ? `tools=${display.tool_count}` : ''
    const names = Array.isArray(display.tool_names) ? display.tool_names.slice(0, 4).join(', ') : ''
    const omitted = display.messages_omitted ? ` (+${display.messages_omitted} hidden)` : ''
    return [turn, msgs, tools, names ? `[${names}]` : '', omitted].filter(Boolean).join('  ')
  }
  if (eventType === 'llm_response') {
    const display = llmPayload(payload)
    const turn = display.turn !== undefined ? `turn=${display.turn}` : ''
    const reason = display.stop_reason ? `stop=${display.stop_reason}` : ''
    const tokens = (display.input_tokens && display.output_tokens)
      ? `tokens=${display.input_tokens}→${display.output_tokens}` : ''
    const calls = display.tool_calls ? `tool_calls=${display.tool_calls}` : ''
    const model = typeof display.model === 'string' ? display.model.split('-').slice(0, 2).join('-') : ''
    return [turn, reason, tokens, calls, model].filter(Boolean).join('  ')
  }
  if (eventType === 'agent_trigger_received') {
    const agent   = typeof payload.agent_id === 'string' ? `agent=${payload.agent_id}` : ''
    const trigger = typeof payload.trigger  === 'string' ? `trigger=${payload.trigger}` : ''
    const pair    = typeof payload.pair     === 'string' ? `pair=${payload.pair}` : ''
    return [agent, trigger, pair].filter(Boolean).join('  ')
  }
  if (eventType === 'agent_trigger_skipped') {
    const agent  = typeof payload.agent_id === 'string' ? `agent=${payload.agent_id}` : ''
    const reason = typeof payload.reason   === 'string' ? `reason=${payload.reason}`   : ''
    const trigger = typeof payload.trigger === 'string' ? `trigger=${payload.trigger}` : ''
    return [agent, reason, trigger].filter(Boolean).join('  ')
  }
  if (eventType === 'agent_signal_generated') {
    const agent    = typeof payload.agent_id  === 'string' ? `agent=${payload.agent_id}` : ''
    const decision = typeof payload.decision  === 'string' ? payload.decision : ''
    const conf     = typeof payload.confidence === 'number' ? `conf=${payload.confidence.toFixed(2)}` : ''
    const signal   = typeof payload.order_start_signal === 'string' ? `start=${payload.order_start_signal}` : ''
    return [agent, decision, conf, signal].filter(Boolean).join('  ')
  }
  if (eventType === 'agent_decision_made') {
    const agent  = typeof payload.agent_id === 'string' ? `agent=${payload.agent_id}` : ''
    const action = typeof payload.action   === 'string' ? payload.action : ''
    const pair   = typeof payload.pair     === 'string' ? `pair=${payload.pair}` : ''
    return [agent, action, pair].filter(Boolean).join('  ')
  }
  if (eventType === 'agent_tool_called') {
    const agent = typeof payload.agent_id  === 'string' ? `agent=${payload.agent_id}` : ''
    const tool  = typeof payload.tool_name === 'string' ? payload.tool_name : ''
    const turn  = payload.turn !== undefined ? `turn=${payload.turn}` : ''
    return [agent, tool, turn].filter(Boolean).join('  ')
  }
  if (eventType === 'agent_tool_result') {
    const agent = typeof payload.agent_id  === 'string' ? `agent=${payload.agent_id}` : ''
    const tool  = typeof payload.tool_name === 'string' ? payload.tool_name : ''
    const ok    = payload.is_error === true ? 'error' : 'ok'
    return [agent, tool, ok].filter(Boolean).join('  ')
  }
  if (eventType === 'llm_turn_started') {
    const agent = typeof payload.agent_id === 'string' ? `agent=${payload.agent_id}` : ''
    const turn  = payload.turn !== undefined ? `turn=${payload.turn}` : ''
    return [agent, turn].filter(Boolean).join('  ')
  }
  if (eventType === 'llm_turn_completed') {
    const agent  = typeof payload.agent_id    === 'string' ? `agent=${payload.agent_id}` : ''
    const turn   = payload.turn !== undefined ? `turn=${payload.turn}` : ''
    const tokens = (payload.input_tokens && payload.output_tokens)
      ? `tokens=${payload.input_tokens}→${payload.output_tokens}` : ''
    return [agent, turn, tokens].filter(Boolean).join('  ')
  }
  if (eventType === 'agent_input_built') {
    const agent = typeof payload.agent_id === 'string' ? `agent=${payload.agent_id}` : ''
    const trigger = typeof payload.trigger === 'string' ? `trigger=${payload.trigger}` : ''
    const source = typeof payload.source === 'string' ? `from=${payload.source}` : ''
    return [agent, trigger, source].filter(Boolean).join('  ')
  }
  if (eventType === 'agent_decision_snapshot_built' || eventType === 'agent_decision_snapshot_invalid') {
    const symbol = typeof payload.symbol === 'string' ? payload.symbol : ''
    const valid = payload.market_data_valid === true ? 'valid=true' : 'valid=false'
    const ts = typeof payload.timestamp === 'string' ? `ts=${payload.timestamp}` : ''
    const features = typeof payload.features === 'object' && payload.features
      ? payload.features as Record<string, unknown>
      : null
    const flags = typeof payload.flags === 'object' && payload.flags
      ? payload.flags as Record<string, unknown>
      : null
    const bias = features && typeof features.dominant_bias_hint === 'string'
      ? `bias=${features.dominant_bias_hint}`
      : ''
    const alignedLong = features && typeof features.core_signals_long === 'number'
      ? `L=${features.core_signals_long}`
      : ''
    const alignedShort = features && typeof features.core_signals_short === 'number'
      ? `S=${features.core_signals_short}`
      : ''
    const range = flags && typeof flags.range_bound === 'boolean'
      ? `range=${flags.range_bound}`
      : ''
    const errors = Array.isArray(payload.errors) && payload.errors.length > 0
      ? `errors=${payload.errors.join(',')}`
      : ''
    return [symbol, valid, bias, alignedLong, alignedShort, range, ts, errors].filter(Boolean).join('  ')
  }
  // Replace escaped quotes from embedded JSON strings (e.g. "{\"key\":\"val\"}") → readable
  const s = JSON.stringify(payload).replace(/\\"/g, '"')
  return s.length > 200 ? s.substring(0, 200) + '…' : s
}

function busSender(payload: Record<string, unknown>): string | null {
  return typeof payload.sender === 'string' && payload.sender.trim()
    ? payload.sender
    : null
}

function payloadMessageId(payload: Record<string, unknown>): string | null {
  return typeof payload.message_id === 'string' && payload.message_id.trim()
    ? payload.message_id
    : null
}

function payloadCorrelationId(payload: Record<string, unknown>): string | null {
  return typeof payload.correlation_id === 'string' && payload.correlation_id.trim()
    ? payload.correlation_id
    : null
}

type DisplayRow = {
  event: MonitoringEvent
  depth: number
  childCount: number
  orphaned: boolean
}

function buildGroupedRows(events: MonitoringEvent[], knownMessageIds?: Set<string>): DisplayRow[] {
  const byMessageId = new Map<string, MonitoringEvent>()
  for (const event of events) {
    const messageId = payloadMessageId(event.payload)
    if (messageId) byMessageId.set(messageId, event)
  }

  const childrenByParent = new Map<string, MonitoringEvent[]>()
  const childIds = new Set<string>()
  const orphanIds = new Set<string>()
  for (const event of events) {
    const correlationId = payloadCorrelationId(event.payload)
    if (!correlationId) continue
    const parent = byMessageId.get(correlationId)
    if (!parent) {
      if (!(knownMessageIds?.has(correlationId) ?? false)) {
        orphanIds.add(event.id)
      }
      continue
    }
    const parentId = payloadMessageId(parent.payload)
    if (!parentId) {
      orphanIds.add(event.id)
      continue
    }
    const siblings = childrenByParent.get(parentId) ?? []
    siblings.push(event)
    childrenByParent.set(parentId, siblings)
    childIds.add(event.id)
  }

  const rows: DisplayRow[] = []
  for (const event of events) {
    if (childIds.has(event.id)) continue
    if (orphanIds.has(event.id)) continue
    const messageId = payloadMessageId(event.payload)
    const children = messageId ? (childrenByParent.get(messageId) ?? []) : []
    rows.push({
      event,
      depth: 0,
      childCount: children.length,
      orphaned: false,
    })
  }
  for (const event of events) {
    if (!orphanIds.has(event.id)) continue
    rows.push({
      event,
      depth: 0,
      childCount: 0,
      orphaned: true,
    })
  }
  rows.sort((a, b) => new Date(b.event.timestamp).getTime() - new Date(a.event.timestamp).getTime())
  return rows
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

  // ── Event type catalogue ────────────────────────────────────────────────────
  const EVENT_INFO: Record<string, { what: string; why: string }> = {
    // LLM
    llm_request:               { what: 'LLM request sent to bus',              why: 'Agent or EC sends an LLM_REQUEST to an LLMService via the event bus' },
    llm_response:              { what: 'LLM service returned response',        why: 'LLMService called Azure/Anthropic API and returns the result to the caller' },
    llm_turn_started:          { what: 'LLM turn started',                     why: 'Agent begins a new turn in the tool-use loop' },
    llm_turn_completed:        { what: 'LLM turn completed',                   why: 'Agent received and processed the LLM response' },
    llm_turn_failed:           { what: 'LLM turn failed',                      why: 'LLM call failed due to timeout or API error' },
    llm_http_attempt_started:  { what: 'HTTP call to LLM provider started',    why: 'LLM Adapter is sending an HTTP request to Azure/OpenAI' },
    llm_http_attempt_completed:{ what: 'HTTP call to LLM provider succeeded',  why: 'LLM provider responded successfully' },
    llm_http_attempt_failed:   { what: 'HTTP call to LLM provider failed',     why: 'LLM provider unreachable or returned an error' },
    // Market data
    m5_candle_trigger:         { what: 'M5 candle triggers agent/EC cycle',    why: 'Broker Adapter received a new M5 candle and forwards it as a trigger to matching AA agents and ECs' },
    m5_candle_update:          { what: 'New M5 candle from broker',            why: 'Broker Adapter fetched a new M5 candle and persisted it to the database' },
    candles_request:           { what: 'Tool requesting candle data',          why: 'get_candles tool requests historical OHLCV data from the DataContainer' },
    candles_response:          { what: 'DataContainer delivering candles',     why: 'DataContainer answers a candles_request with the requested OHLCV series' },
    indicator_request:         { what: 'Tool requesting indicator',            why: 'calculate_indicator tool requests a computed indicator from the DataContainer' },
    indicator_response:        { what: 'DataContainer delivering indicator',   why: 'DataContainer answers an indicator_request with the computed value' },
    swing_levels_request:      { what: 'Tool requesting swing levels',         why: 'get_swing_levels tool requests S/R level computation from the DataContainer' },
    swing_levels_response:     { what: 'DataContainer delivering swing levels',why: 'DataContainer answers with computed highs/lows and nearest S/R levels' },
    // Repository
    repo_request:              { what: 'Database operation requested',         why: 'A tool or agent sends a read/write operation to the RepositoryService' },
    repo_response:             { what: 'RepositoryService responding',         why: 'Database result is returned to the requesting bus member' },
    // Trading
    order_request:             { what: 'Order placement requested',            why: 'Trading tool sends an order request to the Broker Adapter' },
    order_result:              { what: 'Broker adapter confirmed order',       why: 'Order was executed or rejected by the broker' },
    position_close_request:    { what: 'Position close requested',             why: 'close_position tool sends a close request to the Broker Adapter' },
    position_close_result:     { what: 'Broker adapter confirmed close',       why: 'Position was closed or an error was returned' },
    order_modify_request:      { what: 'Order modification requested',         why: 'modify_order tool sends an SL/TP change to the Broker Adapter' },
    order_modify_result:       { what: 'Broker confirmed modification',        why: 'SL/TP adjustment was accepted or rejected' },
    account_status_request:    { what: 'Account status requested',             why: 'Tool requests balance, margin and leverage from the broker' },
    account_status_response:   { what: 'Broker delivering account status',     why: 'Current balance, margin level and allowed risk returned' },
    positions_request:         { what: 'Open positions requested',             why: 'Tool requests the list of currently open trades' },
    positions_response:        { what: 'Open positions delivered',             why: 'Current open positions with direction, price and P&L' },
    // Agent / analysis
    signal_generated:          { what: 'Trading signal generated',             why: 'AA agent completed analysis with BIAS_LONG/SHORT and order_start_signal YES' },
    signal_approved:           { what: 'Signal approved',                      why: 'Signal passed risk validation and is cleared for execution' },
    signal_rejected:           { what: 'Signal rejected',                      why: 'Signal was blocked by risk or quality checks' },
    analysis_result:           { what: 'Analysis result published',            why: 'AA agent completed a full market analysis and sent it into the system' },
    analysis_requested:        { what: 'Analysis requested',                   why: 'A request was sent to an AA agent to perform market analysis' },
    agent_query:               { what: 'Direct query to agent',                why: 'Management API or another agent is asking this agent a direct question' },
    agent_query_response:      { what: 'Agent responding to direct query',     why: 'Response to an agent_query' },
    agent_config_requested:    { what: 'Agent requesting its configuration',   why: 'Agent registered itself and is now loading its config from the ConfigService' },
    agent_config_response:     { what: 'ConfigService delivering agent config',why: 'Agent receives system prompt, tools, snapshot profile and parameters' },
    // EC
    ec_output:                 { what: 'Event Composer published output',      why: 'EC script executed successfully and sends its result — e.g. analysis relay to BA agent' },
    ec_config_requested:       { what: 'EC requesting its configuration',      why: 'Event Composer is starting up and loading its config' },
    ec_config_response:        { what: 'ConfigService delivering EC config',   why: 'EC receives its script, tool config and parameters' },
    // Broker
    broker_connected:          { what: 'Broker connected',                     why: 'Connection to broker server (MT5/OANDA) established successfully' },
    broker_disconnected:       { what: 'Broker disconnected',                  why: 'Connection to broker lost — reconnect will be initiated' },
    broker_reconnecting:       { what: 'Broker reconnecting',                  why: 'Automatic reconnect attempt in progress' },
    broker_error:              { what: 'Broker error',                         why: 'Error occurred during a broker API call' },
    broker_http_request:       { what: 'HTTP request to broker API',           why: 'Broker Adapter is sending a REST call to the MT5/OANDA server' },
    broker_http_response:      { what: 'HTTP response from broker',            why: 'Broker server responded to the API call' },
    sync_check_started:        { what: 'Broker sync check started',            why: 'Broker Adapter is comparing the local order book with the actual broker state' },
    sync_check_completed:      { what: 'Broker sync check completed',          why: 'Discrepancies were identified and the local order book was corrected if needed' },
    order_book_entry_created:  { what: 'Order book entry created',             why: 'A new order was written to the local database' },
    order_book_entry_updated:  { what: 'Order book entry updated',             why: 'An existing order entry was changed (fill, SL/TP, status)' },
    order_book_entry_closed:   { what: 'Order book entry closed',              why: 'Position was closed and P&L was calculated' },
    // Tools
    tool_call_started:         { what: 'Tool call started',                    why: 'ToolDispatcher is executing a tool (via Tool Executor or agent cycle)' },
    tool_call_completed:       { what: 'Tool call completed',                  why: 'Tool returned a result' },
    tool_call_failed:          { what: 'Tool call failed',                     why: 'Tool raised an exception' },
    // System
    agent_input_built:         { what: 'Agent input prepared',                 why: 'Snapshot was built and formatted as user message for the LLM' },
    agent_trigger_received:    { what: 'Agent trigger received',               why: 'Agent received an event and is starting an analysis cycle' },
    agent_trigger_skipped:     { what: 'Agent trigger skipped',                why: 'Agent is paused or the AnyCandle divider has not been reached' },
    agent_signal_generated:    { what: 'Agent generated signal',               why: 'Agent published a tradeable signal to the bus' },
    agent_decision_made:       { what: 'Agent made decision',                  why: 'Agent cycle completed — decision saved to database' },
    routing_reloaded:          { what: 'Routing table reloaded',               why: 'Event routing rules were hot-reloaded — new configuration is active' },
    system_info:               { what: 'System info',                          why: 'General status information from the system or a service' },
    system_error:              { what: 'System error',                         why: 'Unexpected error in a system module' },
    data_container_access:     { what: 'DataContainer accessed',               why: 'DataContainer read or wrote data' },
    m5_candle_saved:           { what: 'M5 candle persisted to database',       why: 'DataContainer saved a new M5 candle to the store and confirms the write' },
    candle_gap_detected:       { what: 'Candle gap detected',                  why: 'DataContainer found a gap in the M5 sequence and requested a repair' },
    m5_candle_fetched:         { what: 'M5 candle fetched from broker',        why: 'Broker Adapter fetched a new candle via API' },
    m5_candle_queued:          { what: 'M5 candle queued to bus',              why: 'New candle is being forwarded into the system' },
    account_status_updated:    { what: 'Account status updated',               why: 'Broker Adapter polled balance/margin and saved the result' },
    agent_alarm:               { what: 'Agent alarm triggered',                why: 'raise_alarm tool was called — manual or automatic alarm' },
  }

  const info = EVENT_INFO[event.event_type]
  const sender = event.payload?.sender as string | undefined
  const target = event.payload?.target as string | undefined
  const messageId = event.payload?.message_id as string | undefined
  const correlationId = event.payload?.correlation_id as string | undefined

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

      {/* Context strip */}
      <div className="flex-shrink-0 px-3 py-2 bg-gray-900/60 border-b border-gray-700 space-y-1 text-xs">
        {/* What / Why */}
        {info ? (
          <div className="space-y-0.5">
            <div className="flex gap-2">
              <span className="text-gray-500 w-12 flex-shrink-0">What</span>
              <span className="text-gray-200">{info.what}</span>
            </div>
            <div className="flex gap-2">
              <span className="text-gray-500 w-12 flex-shrink-0">Why</span>
              <span className="text-gray-400">{info.why}</span>
            </div>
          </div>
        ) : (
          <div className="text-gray-600 italic">No description for event type &quot;{event.event_type}&quot;</div>
        )}
        {/* Sender / Target / Source */}
        <div className="flex flex-wrap gap-x-4 gap-y-0.5 pt-1 border-t border-gray-800">
          {event.source && (
            <div className="flex gap-1">
              <span className="text-gray-500">Source</span>
              <span className="text-sky-400">{event.source}</span>
            </div>
          )}
          {sender && (
            <div className="flex gap-1">
              <span className="text-gray-500">Sender</span>
              <span className="text-emerald-400">{sender}</span>
            </div>
          )}
          {target && (
            <div className="flex gap-1">
              <span className="text-gray-500">Target</span>
              <span className="text-amber-400">{String(target)}</span>
            </div>
          )}
          {event.broker && (
            <div className="flex gap-1">
              <span className="text-gray-500">Broker</span>
              <span className="text-gray-300">{event.broker}{event.pair ? ` · ${event.pair}` : ''}</span>
            </div>
          )}
          {messageId && (
            <div className="flex gap-1">
              <span className="text-gray-500">Msg</span>
              <span className="text-violet-300">{messageId}</span>
            </div>
          )}
          {correlationId && (
            <div className="flex gap-1">
              <span className="text-gray-500">Corr</span>
              <span className="text-fuchsia-300">{correlationId}</span>
            </div>
          )}
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
  activeQuickFilterId: string | null
  savedQuickFilters: SavedMonitorFilter[]
  onSavedQuickFiltersChange: (next: SavedMonitorFilter[]) => void
  onQuickFilterActivated: (filterId: string | null) => void
  onClear: () => void
}

export function EventStream({
  events,
  connected,
  activeQuickFilterId,
  savedQuickFilters,
  onSavedQuickFiltersChange,
  onQuickFilterActivated,
  onClear,
}: EventStreamProps) {
  const [autoScroll, setAutoScroll] = useState(true)
  const [detailEvent, setDetailEvent] = useState<MonitoringEvent | null>(null)
  const [selectedEventId, setSelectedEventId] = useState<string | null>(null)
  const [expandedParents, setExpandedParents] = useState<Record<string, boolean>>({})
  const [filterGroup, setFilterGroup] = useState<MonitorFilterGroup>(() => createFilterGroup())
  const [filterName, setFilterName] = useState('')
  const [loadedFilterId, setLoadedFilterId] = useState<string | null>(null)
  const [includeResponses, setIncludeResponses] = useState(true)
  const [showOrphans, setShowOrphans] = useState(true)
  const [pinnedEvents, setPinnedEvents] = useState<PinnedMonitoringEvent[]>([])
  const [pinnedExpanded, setPinnedExpanded] = useState(true)
  const topRef = useRef<HTMLDivElement>(null)
  const scrollRef = useRef<HTMLDivElement>(null)

  // Poll pinned events every 5 s.
  useEffect(() => {
    let cancelled = false
    const load = () => {
      api.getPinnedEvents()
        .then(list => { if (!cancelled) setPinnedEvents(list) })
        .catch(() => {/* ignore */})
    }
    load()
    const timer = window.setInterval(load, 5_000)
    return () => { cancelled = true; window.clearInterval(timer) }
  }, [])

  const handlePin = (eventId: string) => {
    api.pinEvent(eventId)
      .then(() => api.getPinnedEvents().then(setPinnedEvents))
      .catch(() => {/* ignore */})
  }

  const handleUnpin = (eventId: string) => {
    api.unpinEvent(eventId)
      .then(() => api.getPinnedEvents().then(setPinnedEvents))
      .catch(() => {/* ignore */})
  }

  const pinnedIds = useMemo(() => new Set(pinnedEvents.map(e => e.id)), [pinnedEvents])

  useEffect(() => {
    if (!activeQuickFilterId) return
    const selected = savedQuickFilters.find(item => item.id === activeQuickFilterId)
    if (!selected) return
    setFilterGroup(cloneFilterGroup(selected.definition))
    setFilterName(selected.name)
    setLoadedFilterId(selected.id)
    setIncludeResponses(selected.options.includeResponses)
    setShowOrphans(selected.options.showOrphans)
  }, [activeQuickFilterId, savedQuickFilters])

  const matchingPrimaryEvents = useMemo(() => (
    events.filter(event => isPrimaryEvent(event) && matchesFilterGroup(filterGroup, event))
  ), [events, filterGroup])

  const loadedMessageIds = useMemo(() => (
    new Set(
      events
        .map(event => payloadMessageId(event.payload))
        .filter((value): value is string => value !== null),
    )
  ), [events])

  const matchedPrimaryMessageIds = useMemo(() => (
    new Set(
      matchingPrimaryEvents
        .map(event => payloadMessageId(event.payload))
        .filter((value): value is string => value !== null),
    )
  ), [matchingPrimaryEvents])

  const visible = useMemo(() => (
    [...events.filter(event => {
      if (isPrimaryEvent(event)) return matchesFilterGroup(filterGroup, event)
      if (!includeResponses) return false
      const correlationId = payloadCorrelationId(event.payload)
      if (!correlationId) return false
      if (matchedPrimaryMessageIds.has(correlationId)) return true
      return showOrphans && !loadedMessageIds.has(correlationId)
    })].reverse()
  ), [events, filterGroup, includeResponses, loadedMessageIds, matchedPrimaryMessageIds, showOrphans])

  const groupedTopLevel = buildGroupedRows(visible, loadedMessageIds)
  const groupedVisible: DisplayRow[] = groupedTopLevel.flatMap(row => {
    const messageId = payloadMessageId(row.event.payload)
    if (!messageId || row.childCount === 0) return [row]
    const children = visible.filter(evt => payloadCorrelationId(evt.payload) === messageId)
    const expanded = expandedParents[messageId] === true
    if (!expanded) return [row]
      return [
        row,
        ...children
          .slice()
          .reverse()
      .map(child => ({ event: child, depth: 1, childCount: 0, orphaned: false })),
      ]
  })

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

  const updateRule = <K extends keyof ReturnType<typeof createFilterRule>>(
    ruleId: string,
    key: K,
    value: ReturnType<typeof createFilterRule>[K],
  ) => {
    setFilterGroup(prev => ({
      ...prev,
      rules: prev.rules.map(rule => rule.id === ruleId ? { ...rule, [key]: value } : rule),
    }))
  }

  const addRule = () => {
    setFilterGroup(prev => ({
      ...prev,
      rules: [
        ...prev.rules,
        {
          ...createFilterRule(),
          join: prev.rules.length === 0 ? 'START' : 'AND',
        },
      ],
    }))
  }

  const removeRule = (ruleId: string) => {
    setFilterGroup(prev => ({ ...prev, rules: prev.rules.filter(rule => rule.id !== ruleId) }))
  }

  const resetFilter = () => {
    setFilterGroup(createFilterGroup())
    setFilterName('')
    setLoadedFilterId(null)
    setIncludeResponses(true)
    setShowOrphans(true)
    onQuickFilterActivated(null)
  }

  const saveNewFilter = () => {
    const name = filterName.trim()
    if (!name) return
    const next: SavedMonitorFilter = {
      id: `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`,
      name,
      definition: cloneFilterGroup(filterGroup),
      options: {
        includeResponses,
        showOrphans,
      },
    }
    onSavedQuickFiltersChange([...savedQuickFilters, next])
    setLoadedFilterId(next.id)
    onQuickFilterActivated(next.id)
  }

  const updateSavedFilter = () => {
    if (!loadedFilterId) return
    const name = filterName.trim()
    if (!name) return
    const next = savedQuickFilters.map(filter => (
      filter.id === loadedFilterId
        ? { ...filter, name, definition: cloneFilterGroup(filterGroup), options: { includeResponses, showOrphans } }
        : filter
    ))
    onSavedQuickFiltersChange(next)
    onQuickFilterActivated(loadedFilterId)
  }

  const deleteSavedFilter = () => {
    if (!loadedFilterId) return
    onSavedQuickFiltersChange(savedQuickFilters.filter(filter => filter.id !== loadedFilterId))
    resetFilter()
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
          <span>{visible.length} shown</span>
          <span>·</span>
          <span>{matchingPrimaryEvents.length} primary</span>
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

      <div className="px-3 py-2 bg-gray-900/70 border-b border-gray-800 space-y-2 flex-shrink-0">
        <div className="flex items-center justify-between gap-3 text-xs text-gray-500">
          <div className="flex flex-wrap items-center gap-2 min-w-0">
          <span className="text-gray-300">Filter Builder</span>
          <span>·</span>
          <span>Primary events</span>
          <button
            type="button"
            onClick={addRule}
            className="text-xs px-2 py-1 rounded bg-gray-800 text-gray-300 hover:text-white"
          >
            + Rule
          </button>
          <button
            type="button"
            onClick={resetFilter}
            className="text-xs px-2 py-1 rounded bg-gray-800 text-gray-400 hover:text-white"
          >
            New
          </button>
          <label className="inline-flex items-center gap-2 text-xs text-gray-400">
            <input type="checkbox" checked={includeResponses} onChange={event => setIncludeResponses(event.target.checked)} />
            Include responses
          </label>
          <label className="inline-flex items-center gap-2 text-xs text-gray-400">
            <input type="checkbox" checked={showOrphans} onChange={event => setShowOrphans(event.target.checked)} />
            Show orphans
          </label>
          </div>
          <div className="flex items-center gap-2 flex-shrink-0">
          <input
            value={filterName}
            onChange={event => setFilterName(event.target.value)}
            placeholder="Saved filter name"
            className="bg-gray-900 border border-gray-700 rounded px-2 py-1 text-xs text-gray-200 w-52"
          />
          <button
            type="button"
            onClick={saveNewFilter}
            disabled={!filterName.trim()}
            className="text-xs px-2 py-1 rounded bg-emerald-900/40 text-emerald-300 disabled:opacity-40"
          >
            Save New
          </button>
          <button
            type="button"
            onClick={updateSavedFilter}
            disabled={!loadedFilterId || !filterName.trim()}
            className="text-xs px-2 py-1 rounded bg-gray-800 text-gray-300 disabled:opacity-40"
          >
            Update
          </button>
          <button
            type="button"
            onClick={deleteSavedFilter}
            disabled={!loadedFilterId}
            className="text-xs px-2 py-1 rounded bg-gray-800 text-red-300 disabled:opacity-40"
          >
            Delete
          </button>
          </div>
        </div>

        <div className="space-y-2">
          {filterGroup.rules.length === 0 && (
            <div className="text-xs text-gray-600">No rules. All primary events are shown.</div>
          )}
          {filterGroup.rules.map((rule, index) => (
            <div key={rule.id} className="flex items-center gap-2">
              <select
                value={index === 0 ? 'START' : rule.join}
                onChange={event => updateRule(rule.id, 'join', event.target.value as MonitorFilterJoin)}
                disabled={index === 0}
                className="bg-gray-900 border border-gray-700 rounded px-2 py-1 text-xs text-gray-200 w-28 disabled:opacity-60"
              >
                {RULE_JOIN_OPTIONS
                  .filter(option => index === 0 ? option.value === 'START' : option.value !== 'START')
                  .map(option => <option key={option.value} value={option.value}>{option.label}</option>)}
              </select>
              <select
                value={rule.field}
                onChange={event => updateRule(rule.id, 'field', event.target.value as MonitorFilterField)}
                className="bg-gray-900 border border-gray-700 rounded px-2 py-1 text-xs text-gray-200 w-36"
              >
                {FILTER_FIELDS.map(field => <option key={field.value} value={field.value}>{field.label}</option>)}
              </select>
              <select
                value={rule.operator}
                onChange={event => updateRule(rule.id, 'operator', event.target.value as MonitorFilterOperator)}
                className="bg-gray-900 border border-gray-700 rounded px-2 py-1 text-xs text-gray-200 w-28"
              >
                {FILTER_OPERATORS.map(operator => <option key={operator.value} value={operator.value}>{operator.label}</option>)}
              </select>
              {rule.field === 'payload' && (
                <input
                  value={rule.path ?? ''}
                  onChange={event => updateRule(rule.id, 'path', event.target.value)}
                  placeholder="payload.path"
                  className="bg-gray-900 border border-gray-700 rounded px-2 py-1 text-xs text-gray-200 w-40"
                />
              )}
              {rule.operator !== 'exists' && (
                <input
                  value={rule.value}
                  onChange={event => updateRule(rule.id, 'value', event.target.value)}
                  placeholder="value"
                  className="flex-1 min-w-0 bg-gray-900 border border-gray-700 rounded px-2 py-1 text-xs text-gray-200"
                />
              )}
              <button
                type="button"
                onClick={() => removeRule(rule.id)}
                className="text-xs px-2 py-1 rounded bg-gray-800 text-gray-400 hover:text-red-300"
              >
                Remove
              </button>
            </div>
          ))}
        </div>
      </div>

      {/* Event list */}
      {/* ── Pinned events panel ─────────────────────────────────────────── */}
      {pinnedEvents.length > 0 && (
        <div className="flex-shrink-0 border-b border-amber-700/50 bg-amber-950/20">
          <button
            onClick={() => setPinnedExpanded(v => !v)}
            className="w-full flex items-center gap-2 px-3 py-1.5 text-xs text-amber-300 hover:text-amber-100 transition-colors"
          >
            <Pin className="w-3 h-3" />
            <span className="font-medium">Pinned Events ({pinnedEvents.length})</span>
            <span className="ml-auto text-gray-500">{pinnedExpanded ? '▲' : '▼'}</span>
          </button>
          {pinnedExpanded && (
            <div className="font-mono text-xs px-2 pb-2 space-y-0.5 max-h-48 overflow-y-auto">
              {[...pinnedEvents].reverse().map(pe => (
                <div
                  key={pe.id}
                  onDoubleClick={() => { setDetailEvent(pe); setSelectedEventId(pe.id) }}
                  className="flex gap-2 px-1 py-0.5 rounded hover:bg-amber-900/20 cursor-pointer border-l-2 border-amber-600/50"
                  title="Double-click to inspect"
                >
                  <span className="text-gray-600 flex-shrink-0 w-44">{formatTs(pe.timestamp)}</span>
                  <span className={`flex-shrink-0 w-36 truncate ${eventColour(pe.event_type)}`}>{pe.event_type}</span>
                  {pe.auto_pinned && (
                    <span className="flex-shrink-0 text-[10px] uppercase tracking-wide text-amber-400 bg-amber-900/40 border border-amber-700/50 rounded px-1">auto</span>
                  )}
                  {pe.source?.startsWith('agent:') && (
                    <span className="text-sky-400 flex-shrink-0 max-w-48 truncate">{pe.source.slice('agent:'.length)}</span>
                  )}
                  <span className="text-gray-400 truncate">{formatPayload(pe.event_type, pe.payload)}</span>
                  <button
                    onClick={e => { e.stopPropagation(); handleUnpin(pe.id) }}
                    title="Remove pin"
                    className="ml-auto flex-shrink-0 text-gray-600 hover:text-red-400 transition-colors"
                  >
                    <PinOff className="w-3 h-3" />
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      <div
        ref={scrollRef}
        onScroll={handleScroll}
        className="flex-1 overflow-y-auto font-mono text-xs bg-gray-950 p-2 space-y-0.5"
      >
        {/* Sentinel at the TOP — auto-scroll jumps here when new events arrive */}
        <div ref={topRef} />
        {groupedVisible.length === 0 && (
          <div className="text-gray-600 text-center py-8">
            {connected ? 'Waiting for events…' : 'Not connected — check backend'}
          </div>
        )}
        {groupedVisible.map(({ event: evt, depth, childCount, orphaned }) => {
          const messageId = payloadMessageId(evt.payload)
          const hasChildren = childCount > 0 && messageId !== null
          const expanded = messageId ? expandedParents[messageId] === true : false
          const llmKind = llmOrigin(evt)
          return (
          <div
            key={evt.id}
            onDoubleClick={() => { setDetailEvent(evt); setSelectedEventId(evt.id) }}
            className={[
              'group flex gap-2 px-1 py-0.5 rounded cursor-pointer select-none border-l-2',
              depth > 0 ? 'ml-6 bg-gray-900/30' : '',
              selectedEventId === evt.id
                ? 'bg-orange-950/80 border-emerald-500'
                : orphaned
                  ? 'hover:bg-gray-900/50 border-orange-500 bg-orange-950/20'
                  : 'hover:bg-gray-900/50 border-transparent',
            ].join(' ')}
            title="Double-click to inspect"
            >
              <span className="flex-shrink-0 w-10 text-center">
              {hasChildren ? (
                <button
                  type="button"
                  onClick={(event) => {
                    event.stopPropagation()
                    setExpandedParents(prev => ({ ...prev, [messageId]: !expanded }))
                  }}
                  className="text-[11px] text-amber-300 hover:text-amber-200 transition-colors"
                  title={expanded ? 'Hide correlated events' : 'Show correlated events'}
                >
                  [{childCount}]
                </button>
              ) : null}
              </span>
              <span className="text-gray-600 flex-shrink-0 w-44">{formatTs(evt.timestamp)}</span>
              {orphaned && (
              <span
                className="flex-shrink-0 text-[11px] text-orange-300 w-16"
                title="Response with correlation_id but no visible parent request in current buffer"
              >
                orphan
              </span>
            )}
            <span className={`flex-shrink-0 w-36 truncate ${eventColour(evt.event_type)}`}>
              {evt.event_type}
            </span>
            {llmKind && (
              <span
                className={`flex-shrink-0 text-[11px] uppercase tracking-wide w-14 ${
                  llmKind === 'bus' ? 'text-violet-300' : 'text-sky-300'
                }`}
                title={llmKind === 'bus' ? 'EventBus transport event' : 'Agent monitoring event'}
              >
                {llmKind}
              </span>
            )}
            {evt.event_type === 'event_bus_message' && busSender(evt.payload) && (
              <span className="text-purple-300 flex-shrink-0 max-w-64 truncate">
                [{busSender(evt.payload)}]
              </span>
            )}
            {evt.source && evt.source.startsWith('agent:') && (
              <span className="text-sky-400 flex-shrink-0 max-w-64 truncate">
                {evt.source.slice('agent:'.length)}
              </span>
            )}
            {evt.broker && (
              <span className="text-gray-500 flex-shrink-0">[{evt.broker}{evt.pair ? `·${evt.pair}` : ''}]</span>
            )}
            <span className="text-gray-400 truncate">
              {formatPayload(evt.event_type, evt.payload)}
            </span>
            <button
              onClick={e => { e.stopPropagation(); pinnedIds.has(evt.id) ? handleUnpin(evt.id) : handlePin(evt.id) }}
              title={pinnedIds.has(evt.id) ? 'Unpin event' : 'Pin event'}
              className={`ml-auto flex-shrink-0 transition-colors ${
                pinnedIds.has(evt.id)
                  ? 'text-amber-400 hover:text-red-400'
                  : 'text-transparent group-hover:text-gray-500 hover:!text-amber-400'
              }`}
            >
              {pinnedIds.has(evt.id)
                ? <PinOff className="w-3 h-3" />
                : <Pin className="w-3 h-3" />}
            </button>
          </div>
          )
        })}
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

export type { SavedMonitorFilter } from './filtering'


