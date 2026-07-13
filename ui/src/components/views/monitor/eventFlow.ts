/**
 * eventFlow — central mapping that decides for each event type and module tab:
 *   (a) is the event visible in this tab?
 *   (b) which arrow to show ('<' from-module, '>' to-module, '!' informational)
 *
 * For `event_bus_message` the direction is dynamic — derived per message from
 * `payload.sender` / `payload.target` / `payload.event`.
 *
 * This file is the single source of truth for the Monitor's flow visualization.
 * Edit here if a routing flaw needs reflecting.
 */
import type { MonitoringEvent } from '@/api/client'

export type ModuleTab = 'llm' | 'tool' | 'bus' | 'broker' | 'data' | 'core' | 'agent' | 'entity'
export type FlowArrow = '<' | '>' | '!'

interface StaticFlow {
  /** For each module tab where this event is visible, what arrow */
  tabs: Partial<Record<ModuleTab, FlowArrow>>
}

/**
 * Static per-MonitoringEventType mapping.
 *
 * Direction is interpreted relative to the **selected tab's module**:
 *   '<' = leaving the module (outgoing / module is the originator)
 *   '>' = entering the module (incoming / module is the recipient)
 *   '!' = informational (no clear direction)
 */
const STATIC_EVENT_FLOW: Record<string, StaticFlow> = {
  // ── LLM lifecycle ───────────────────────────────────────────────────────────
  llm_request:               { tabs: { llm: '>' } },
  llm_turn_started:          { tabs: { llm: '>' } },
  llm_http_attempt_started:  { tabs: { llm: '>' } },
  llm_response:              { tabs: { llm: '<' } },
  llm_error:                 { tabs: { llm: '<' } },
  llm_turn_completed:        { tabs: { llm: '<' } },
  llm_turn_failed:           { tabs: { llm: '<' } },
  llm_http_attempt_completed: { tabs: { llm: '<' } },
  llm_http_attempt_failed:   { tabs: { llm: '<' } },

  // ── Tool dispatcher ─────────────────────────────────────────────────────────
  tool_call_started:    { tabs: { tool: '>' } },
  agent_tool_called:    { tabs: { tool: '>' } },
  tool_call_completed:  { tabs: { tool: '<' } },
  tool_call_failed:     { tabs: { tool: '<' } },
  agent_tool_result:    { tabs: { tool: '<' } },

  // ── Broker / Broker-Adapter (AD) ────────────────────────────────────────────
  broker_http_request:         { tabs: { broker: '>' } },
  broker_http_response:        { tabs: { broker: '<' } },
  broker_connected:            { tabs: { broker: '<' } },
  broker_disconnected:         { tabs: { broker: '<' } },
  broker_reconnecting:         { tabs: { broker: '<' } },
  broker_error:                { tabs: { broker: '<' } },
  account_status_updated:      { tabs: { broker: '<' } },
  account_poll_error:          { tabs: { broker: '<' } },
  order_book_entry_created:    { tabs: { broker: '<' } },
  order_book_entry_updated:    { tabs: { broker: '<' } },
  order_book_entry_closed:     { tabs: { broker: '<' } },
  sync_check_started:          { tabs: { broker: '>' } },
  sync_check_completed:        { tabs: { broker: '<' } },
  sync_order_book_updated:     { tabs: { broker: '<' } },
  sync_discrepancy_found:      { tabs: { broker: '!' } },
  sync_agent_notified:         { tabs: { broker: '!' } },

  // M5 candle pipeline — emitted by AD (broker adapter), enters data layer
  m5_candle_fetched: { tabs: { broker: '<', data: '>' } },
  m5_candle_queued:  { tabs: { broker: '<' } },

  // ── Data layer ──────────────────────────────────────────────────────────────
  candle_repair_started:    { tabs: { data: '>' } },
  candle_repair_completed:  { tabs: { data: '<' } },
  candle_repair_failed:     { tabs: { data: '<' } },
  candle_gap_detected:      { tabs: { data: '!' } },
  timeframe_calculated:     { tabs: { data: '!' } },
  data_container_access:    { tabs: { data: '!' } },

  // ── Core / Runtime ──────────────────────────────────────────────────────────
  agent_trigger_received:   { tabs: { core: '<' } },   // core delivered trigger
  agent_trigger_skipped:    { tabs: { core: '!' } },   // core decision, nothing sent
  agent_backlog_detected:   { tabs: { core: '!' } },
  agent_queue_full:         { tabs: { core: '!' } },
  routing_reloaded:         { tabs: { core: '<', bus: '!' } },
  routing_reload_failed:    { tabs: { core: '<', bus: '!' } },
  system_error:             { tabs: { core: '!' } },
  system_warning:           { tabs: { core: '!' } },
  system_info:              { tabs: { core: '!' } },

  // ── Entity / EC ─────────────────────────────────────────────────────────────
  ec_run_started:    { tabs: { entity: '>' } },
  ec_run_completed:  { tabs: { entity: '<' } },
  ec_run_failed:     { tabs: { entity: '!' } },
  ec_run_output:     { tabs: { entity: '<' } },

  // ── Broker execution (bus-based) ──────────────────────────────────────────
  order_request:            { tabs: { agent: '<', broker: '>' } },
  order_result:             { tabs: { broker: '<', agent: '>' } },
  position_close_request:   { tabs: { agent: '<', broker: '>' } },
  position_close_result:    { tabs: { broker: '<', agent: '>' } },
  order_modify_request:     { tabs: { agent: '<', broker: '>' } },
  order_modify_result:      { tabs: { broker: '<', agent: '>' } },
  account_status_request:   { tabs: { agent: '<', broker: '>' } },
  account_status_response:  { tabs: { broker: '<', agent: '>' } },
  positions_request:        { tabs: { agent: '<', broker: '>' } },
  positions_response:       { tabs: { broker: '<', agent: '>' } },

  // ── DataContainer queries (bus-based) ────────────────────────────────────
  candles_request:          { tabs: { agent: '<', data: '>' } },
  candles_response:         { tabs: { data: '<', agent: '>' } },
  indicator_request:        { tabs: { agent: '<', data: '>' } },
  indicator_response:       { tabs: { data: '<', agent: '>' } },
  swing_levels_request:     { tabs: { agent: '<', data: '>' } },
  swing_levels_response:    { tabs: { data: '<', agent: '>' } },
  candle_data_bulk:         { tabs: { broker: '<', data: '>' } },

  // ── Repository service ────────────────────────────────────────────────────
  repo_request:             { tabs: { agent: '<', core: '>' } },
  repo_response:            { tabs: { core: '<', agent: '>' } },

  // ── Agent (AA/BA/GA fachliche Outputs) ──────────────────────────────────────
  agent_signal_generated:           { tabs: { agent: '<' } },
  agent_decision_made:              { tabs: { agent: '<' } },
  agent_alarm:                      { tabs: { agent: '<' } },
  agent_input_built:                { tabs: { agent: '!' } },
  agent_decision_snapshot_built:    { tabs: { agent: '!' } },
  agent_decision_snapshot_invalid:  { tabs: { agent: '!' } },
}

/**
 * Classifies an agent_id (e.g. "OXS_T-EURUSD-AD-ADPT") into a coarse module
 * category. The third dash-segment indicates the agent kind:
 *   AD → broker (broker adapter)
 *   AA, BA, GA → agent (analysis / broker action / general agent)
 * Anything else (management API, runtime, unknown) → core.
 */
function classifyAgentId(agentId: string | null | undefined): ModuleTab | 'unknown' {
  if (!agentId || typeof agentId !== 'string') return 'unknown'

  // Named system services — explicit mapping
  if (agentId === 'SYSTM-ALL___-GA-DATA')  return 'data'
  if (agentId === 'SYSTM-ALL___-GA-REPO')  return 'core'
  if (agentId === 'SYSTM-ALL___-GA-CFGSV') return 'core'
  if (agentId === 'MGMT_-ALL___-GA-MGMT')  return 'core'
  if (agentId === 'eventbus' || agentId === 'management_api' || agentId === 'runtime') return 'core'

  const parts = agentId.split('-')
  // Expect format BROKER-PAIR-KIND-NAME, kind is parts[2]
  if (parts.length >= 3) {
    const kind = parts[2].toUpperCase()
    if (kind === 'AD') return 'broker'
    if (kind === 'AA' || kind === 'BA' || kind === 'GA') return 'agent'
    if (kind === 'EC') return 'entity'
  }
  return 'unknown'
}

/**
 * For an `event_bus_message`, compute which module tabs the message belongs to
 * and what arrow each tab should display.
 *
 * The bus message has a sender (origin) and a target (destination). The arrow
 * is relative to the selected tab:
 *   - module == sender   → '<' (leaving that module)
 *   - module == target   → '>' (entering that module)
 *   - module is neither  → not visible in that tab
 *
 * The bus tab always shows every bus message as informational transit ('!').
 */
function busMessageFlow(payload: Record<string, unknown>): Partial<Record<ModuleTab, FlowArrow>> {
  const out: Partial<Record<ModuleTab, FlowArrow>> = { bus: '!' }

  const senderId = typeof payload.sender === 'string' ? payload.sender : null
  // target may be a single string or an array of strings (multi-target routing)
  const targetRaw = payload.target
  const targetIds: string[] = Array.isArray(targetRaw)
    ? targetRaw.filter((t): t is string => typeof t === 'string')
    : typeof targetRaw === 'string' ? [targetRaw] : []
  const targetId = targetIds[0] ?? null
  const senderMod = classifyAgentId(senderId)
  const targetMod = classifyAgentId(targetId)

  // Specific inner event types route to dedicated tabs even when sender/target
  // classification is unknown (e.g. management_api requesting config).
  const innerEvent = typeof payload.event === 'string' ? payload.event : ''
  if (innerEvent === 'agent_config_response') {
    out.core = '<'
    if (targetMod === 'agent') out.agent = '>'
    return out
  }
  if (innerEvent === 'agent_config_requested') {
    out.core = '>'
    if (senderMod === 'agent') out.agent = '<'
    return out
  }
  if (innerEvent === 'ec_config_response') {
    out.core = '<'
    if (targetMod === 'entity') out.entity = '>'
    return out
  }
  if (innerEvent === 'ec_config_requested') {
    out.core = '>'
    if (senderMod === 'entity') out.entity = '<'
    return out
  }
  if (innerEvent === 'ec_output') {
    if (senderMod === 'entity') out.entity = '<'
    if (targetMod !== 'unknown') out[targetMod] = '>'
    return out
  }
  // DataContainer data requests/responses
  if (innerEvent === 'candles_request' || innerEvent === 'indicator_request' || innerEvent === 'swing_levels_request') {
    if (senderMod !== 'unknown') out[senderMod] = '<'
    out.data = '>'
    return out
  }
  if (innerEvent === 'candles_response' || innerEvent === 'indicator_response' || innerEvent === 'swing_levels_response') {
    out.data = '<'
    if (targetMod !== 'unknown' && targetMod !== 'data') out[targetMod] = '>'
    return out
  }
  // Repository requests/responses
  if (innerEvent === 'repo_request') {
    if (senderMod !== 'unknown') out[senderMod] = '<'
    out.core = '>'
    return out
  }
  if (innerEvent === 'repo_response') {
    out.core = '<'
    if (targetMod !== 'unknown' && targetMod !== 'core') out[targetMod] = '>'
    return out
  }
  if (innerEvent === 'agent_query' || innerEvent === 'agent_query_response') {
    if (senderMod !== 'unknown' && senderMod !== 'bus') out[senderMod] = '<'
    if (targetMod !== 'unknown' && targetMod !== 'bus') out[targetMod] = '>'
    return out
  }

  // Default: derive from sender + all resolved target module classifications
  if (senderMod !== 'unknown' && senderMod !== 'bus') {
    out[senderMod] = '<'
  }
  const allTargetMods = new Set(targetIds.map(classifyAgentId))
  for (const mod of allTargetMods) {
    if (mod !== 'unknown' && mod !== 'bus' && mod !== senderMod) {
      out[mod] = '>'
    }
  }

  return out
}

/**
 * Returns the flow map for a given monitoring event — which tabs it appears in
 * and the arrow per tab. For `event_bus_message` the result is computed from
 * the message payload; otherwise the static table is consulted.
 */
export function getEventFlow(evt: MonitoringEvent): Partial<Record<ModuleTab, FlowArrow>> {
  if (evt.event_type === 'event_bus_message') {
    return busMessageFlow(evt.payload || {})
  }
  const entry = STATIC_EVENT_FLOW[evt.event_type]
  return entry ? entry.tabs : {}
}

/**
 * Convenience: should this event appear in the given module tab?
 * For the 'all' pseudo-tab this is always true.
 */
export function eventVisibleInTab(evt: MonitoringEvent, tab: ModuleTab | 'all'): boolean {
  if (tab === 'all') return true
  return getEventFlow(evt)[tab] !== undefined
}

/**
 * Convenience: arrow character for an event in a given tab (or null when not visible).
 */
export function eventArrowInTab(evt: MonitoringEvent, tab: ModuleTab): FlowArrow | null {
  return getEventFlow(evt)[tab] ?? null
}
