/**
 * API client — thin wrappers around fetch() for the FastAPI management API.
 *
 * During development Vite proxies all requests to http://127.0.0.1:8765.
 * In production the React bundle is served by the same FastAPI process so
 * relative paths just work.
 */

const BASE = ''  // relative — works for both dev proxy and production

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`)
  if (!res.ok) {
    const text = await res.text()
    throw new Error(`GET ${path} → ${res.status}: ${text}`)
  }
  return res.json() as Promise<T>
}

async function getText(path: string): Promise<string> {
  const res = await fetch(`${BASE}${path}`)
  const raw = await res.text()
  if (!res.ok) {
    throw new Error(`GET ${path} → ${res.status}: ${raw}`)
  }
  const contentType = (res.headers.get('content-type') || '').toLowerCase()
  if (!contentType.includes('application/json')) {
    const preview = raw.slice(0, 120).replace(/\s+/g, ' ').trim()
    throw new Error(
      `GET ${path} returned non-JSON response (${contentType || 'unknown'}): ${preview}`,
    )
  }
  let parsed: unknown
  try {
    parsed = JSON.parse(raw)
  } catch {
    throw new Error(`GET ${path} returned invalid JSON payload`)
  }
  if (!parsed || typeof parsed !== 'object' || typeof (parsed as { text?: unknown }).text !== 'string') {
    throw new Error(`GET ${path} JSON payload does not contain a string field 'text'`)
  }
  return (parsed as { text: string }).text
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    const text = await res.text()
    let detail = text
    try {
      const parsed = JSON.parse(text) as { detail?: unknown }
      if (parsed && typeof parsed === 'object' && parsed.detail !== undefined) {
        detail = typeof parsed.detail === 'string'
          ? parsed.detail
          : JSON.stringify(parsed.detail)
      }
    } catch {
      // Keep raw text when response is not JSON.
    }
    throw new Error(`POST ${path} → ${res.status}: ${detail}`)
  }
  return res.json() as Promise<T>
}

async function put<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(`PUT ${path} -> ${res.status}: ${text}`)
  }
  return res.json() as Promise<T>
}

// ── Exported API calls ────────────────────────────────────────────────────────

export const api = {
  getVersion:     () => get<{ version: string }>('/version'),
  getHealth:      () => get<{ status: string; uptime_seconds: number; registered_agents: number }>('/health'),
  getRuntimeStatus: () => get<{ agents: string[]; routing_rules: number; uptime_seconds: number }>('/runtime/status'),
  getInitialConsole: () => get<InitialConsoleResponse>('/console/initial'),
  getSystemUpdateStatus: () => get<SystemUpdateStatusResponse>('/system/update/status'),
  startSystemUpdate: (body: SystemUpdateStartRequest) => post<{ status: string; requested_version?: string | null }>('/system/update/start', body),
  restartSystemNow: () => post<{ status: string; signal?: string; mode?: string }>('/system/restart-now', {}),
  pauseRuntime: () => post<{ status: string; runtime_paused: boolean }>('/system/runtime/pause', {}),
  resumeRuntime: () => post<{ status: string; runtime_paused: boolean }>('/system/runtime/resume', {}),
  getAgents:      () => get<AgentInfo[]>('/agents'),
  getComposers:   () => get<{ ec_id: string }[]>('/composers'),
  executeComposer: (ecId: string, input: Record<string, unknown>) =>
                    post<ECExecuteResponse>(`/composers/${encodeURIComponent(ecId)}/execute`, { input }),
  askAgent:       (agentId: string, question: string, timeout = 120, history?: Array<{role: string, content: string}>) =>
                    post<AgentQueryResponse>(`/agents/${encodeURIComponent(agentId)}/ask`, { question, timeout, ...(history?.length ? { history } : {}) }),
  executeAgent:   (agentId: string, body: AgentExecuteRequest) =>
                    post<AgentExecuteResponse>(`/agents/${encodeURIComponent(agentId)}/execute`, body),
  getAgentCandles: (agentId: string, timeframe = 'M5', count = 100) =>
                    get<CandleBar[]>(
                      `/agents/${encodeURIComponent(agentId)}/candles?timeframe=${encodeURIComponent(timeframe)}&count=${count}`,
                    ),
  triggerAgent:    (agentId: string) =>
                    post<{ message_id: string; status: string; broker_name: string; pair: string; candle_timestamp: string }>(
                      `/agents/${encodeURIComponent(agentId)}/trigger`, {}),
  triggerComposer: (ecId: string) =>
                    post<{ message_id: string; status: string; broker_name: string; pair: string; candle_timestamp: string }>(
                      `/composers/${encodeURIComponent(ecId)}/trigger`, {}),
  getPinnedEvents: () => get<PinnedMonitoringEvent[]>('/monitoring/pinned'),
  pinEvent:        (eventId: string) => post<{ event_id: string; pinned: boolean }>(`/monitoring/events/${encodeURIComponent(eventId)}/pin`, {}),
  unpinEvent:      (eventId: string) => {
                    return fetch(`${''}/monitoring/events/${encodeURIComponent(eventId)}/pin`, { method: 'DELETE' })
                      .then(async res => {
                        if (!res.ok) { const t = await res.text(); throw new Error(`DELETE /monitoring/events/${eventId}/pin → ${res.status}: ${t}`) }
                        return res.json() as Promise<{ event_id: string; pinned: boolean }>
                      })
                  },
  getOrderbookEntries: (params?: {
                    broker_name?: string | null
                    pair?: string | null
                    status_filter?: string
                    limit?: number
                  }) => {
                    const query = new URLSearchParams()
                    if (params?.broker_name) query.set('broker_name', params.broker_name)
                    if (params?.pair) query.set('pair', params.pair)
                    if (params?.status_filter) query.set('status_filter', params.status_filter)
                    if (params?.limit) query.set('limit', String(params.limit))
                    const suffix = query.toString() ? `?${query.toString()}` : ''
                    return get<OrderbookEntrySummary[]>(`/orderbook${suffix}`)
                  },
  getOrderbookEntry: (entryId: string) =>
                    get<OrderbookEntryDetail>(`/orderbook/${encodeURIComponent(entryId)}`),
  getOrderbookCandles: (entryId: string, timeframe = 'M5', count = 2000) =>
                    get<CandleBar[]>(
                      `/orderbook/${encodeURIComponent(entryId)}/candles?timeframe=${encodeURIComponent(timeframe)}&count=${count}`,
                    ),
  getCandles: (pair: string, timeframe = 'M5', count = 200, broker_name?: string | null) => {
                    const q = new URLSearchParams({ pair, timeframe, count: String(count) })
                    if (broker_name) q.set('broker_name', broker_name)
                    return get<CandleBar[]>(`/candles?${q.toString()}`)
                  },
  getAnalyses: (params?: {
                    agent_id?: string | null
                    pair?: string | null
                    limit?: number
                  }) => {
                    const query = new URLSearchParams()
                    if (params?.agent_id) query.set('agent_id', params.agent_id)
                    if (params?.pair) query.set('pair', params.pair)
                    if (params?.limit) query.set('limit', String(params.limit))
                    const suffix = query.toString() ? `?${query.toString()}` : ''
                    return get<AnalysisRecord[]>(`/analyses${suffix}`)
                  },
  getAnalysis: (recordId: string) =>
                    get<AnalysisRecord>(`/analyses/${encodeURIComponent(recordId)}`),
  getTools:       () => get<{ tools: ToolInfo[] }>('/tools'),
  executeTool:    (
                    tool_name: string,
                    arguments_: Record<string, unknown>,
                    agent_id?: string | null,
                    broker_name?: string | null,
                    llm_name?: string | null,
                    pair?: string | null,
                  ) =>
                    post<ToolExecuteResponse>("/tools/execute", {
                      tool_name,
                      arguments: arguments_,
                      agent_id: agent_id || null,
                      broker_name: broker_name || null,
                      llm_name: llm_name || null,
                      pair: pair || null,
                    }),
  calculateIndicator: (params: {
                    indicator: string
                    period: number
                    timeframe: string
                    history: number
                    broker_name?: string | null
                    pair?: string | null
                    agent_id?: string | null
                    smooth_period?: number
                  }) =>
                    post<ToolExecuteResponse>('/tools/execute', {
                      tool_name: 'calculate_indicator',
                      arguments: {
                        indicator: params.indicator,
                        period: params.period,
                        timeframe: params.timeframe,
                        history: params.history,
                        ...(params.smooth_period && params.smooth_period > 1 ? { smooth_period: params.smooth_period } : {}),
                      },
                      broker_name: params.broker_name || null,
                      pair: params.pair || null,
                      agent_id: params.agent_id || null,
                    }).then(r => r.result as { indicator: string; period: number; timeframe: string; history: number; values: IndicatorValue[] }),
  runLlmChecker: (body: LlmCheckerRequest) => post<LlmCheckerResponse>('/test/llm/check', body),
  getProjectRoot:  () => get<{ root: string }>('/config/root'),
  getDocFile:      (filename: string) => getText(`/docs/${encodeURIComponent(filename)}`),
  saveDocFile:     async (filename: string, content: string): Promise<void> => {
    const res = await fetch(`/docs/${encodeURIComponent(filename)}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'text/plain; charset=utf-8' },
      body: content,
    })
    if (!res.ok) { const t = await res.text(); throw new Error(`PUT /docs/${filename} → ${res.status}: ${t}`) }
  },
  getConfigView:   () => get<Record<string, unknown>>('/config/view'),
  getProjectReadmeText: () => getText('/config/information/readme'),
  saveProjectReadmeText: (content: string) =>
                    put<{ status: string; file: string }>('/config/information/readme', content),
  getSystemConfig: () => get<Record<string, unknown>>('/config/system'),
  getSystemConfigText: () => getText('/config/system/text'),
  getSystemConfigMeta: () => get<{ text: string; file: string }>('/config/system/text'),
  saveSystemConfig: (content: Record<string, unknown> | string) =>
                    put<{ status: string; file: string }>('/config/system', content),
  getSnapshotHelpersText: () => getText('/config/helpers/snapshot/text'),
  getSnapshotHelpersMeta: () => get<{ text: string; file: string }>('/config/helpers/snapshot/text'),
  saveSnapshotHelpersText: (content: string) =>
                    put<{ status: string; file: string }>('/config/helpers/snapshot', content),
  previewSnapshot: (body: SnapshotPreviewRequest) =>
                    post<SnapshotPreviewResponse>('/config/snapshots/preview', body),
  previewSnapshotTool: (body: SnapshotToolPreviewRequest) =>
                    post<SnapshotToolPreviewResponse>('/config/snapshots/tool-preview', body),
  previewSnapshotCalculation: (body: SnapshotCalculationPreviewRequest) =>
                    post<SnapshotCalculationPreviewResponse>('/config/snapshots/calculation-preview', body),
  testDecisionPromptScript: (body: DecisionPromptScriptTestRequest) =>
                    post<DecisionPromptScriptTestResponse>('/config/decision-prompt/test-script', body),
  getConfigFile:   (name: string) => get<Record<string, unknown>>(`/config/files/${name}`),
  getConfigFileText: (name: string) => getText(`/config/files/${name}/text`),
  saveConfigFile:  (name: string, content: Record<string, unknown> | string) =>
                    put<{ status: string; file: string }>(`/config/files/${name}`, content),
  getModuleNames:  (moduleType: string) =>
                     get<{ names: string[] }>(`/config/modules/${moduleType}`),
  getModuleConfig: (moduleType: string, name: string) =>
                     get<Record<string, unknown>>(`/config/modules/${moduleType}/${name}`),
  getModuleConfigRaw: (moduleType: string, name: string) =>
                     get<Record<string, unknown>>(`/config/modules/${moduleType}/${name}/raw`),
  getModuleConfigRawText: (moduleType: string, name: string) =>
                     getText(`/config/modules/${moduleType}/${name}/raw_text`),
  saveModuleConfigRaw: (moduleType: string, name: string, content: Record<string, unknown> | string) =>
                     put<{ status: string; file: string }>(`/config/modules/${moduleType}/${name}/raw`, content),
  exportAgentPackage: (body: PackageExportRequest) => post<PackageExportResponse>('/config/packages/export', body),
  validateAgentPackage: (body: PackageValidateRequest) => post<PackageValidationResponse>('/config/packages/validate', body),
  importAgentPackage: (body: PackageImportRequest) => post<PackageImportResponse>('/config/packages/import', body),
  injectEvent:     (body: EventInjectRequest) => post<{ message_id: string }>('/events', body),
  getPromptLibrary: (scope: string) => get<PromptLibrary>(`/config/prompt-library/${scope}`),
  savePromptLibrary: (scope: string, library: PromptLibrary) =>
                    put<{ status: string; file: string }>(`/config/prompt-library/${scope}`, library),
  getSnippetLibrary: (scope: string) => get<SnippetLibrary>(`/config/snippet-library/${scope}`),
  saveSnippetLibrary: (scope: string, library: SnippetLibrary) =>
                    put<{ status: string; file: string }>(`/config/snippet-library/${scope}`, library),
  llmAssistantChat: (req: LLMAssistantChatRequest) =>
                    post<LLMAssistantChatResponse>('/llm-assistant/chat', req),

  // ── Knowledge base ──────────────────────────────────────────────────────────
  kbListDocuments: () => get<KbDocMeta[]>('/kb/documents'),
  kbGetDocument:   (id: string) => get<KbDoc>(`/kb/documents/${encodeURIComponent(id)}`),
  kbCreateDocument: (body: Partial<KbDoc>) => post<{ id: string }>('/kb/documents', body),
  kbUpdateDocument: (id: string, body: Partial<KbDoc>) =>
                    put<{ ok: boolean }>(`/kb/documents/${encodeURIComponent(id)}`, body),
  kbDeleteDocument: (id: string) =>
                    (fetch(`/kb/documents/${encodeURIComponent(id)}`, { method: 'DELETE' }).then(r => r.json())),
  kbSearch: (q: string) => get<KbSearchResult[]>(`/kb/search?q=${encodeURIComponent(q)}`),

  // ── LLM Contexts ──────────────────────────────────────────────────────────
  llmContextList: () => get<string[]>('/llm-contexts'),
  llmContextGet:  (filename: string) => get<{ filename: string; content: string }>(`/llm-contexts/${encodeURIComponent(filename)}`),
  llmContextSave: (filename: string, content: string) =>
    fetch(`/llm-contexts/${encodeURIComponent(filename)}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content }),
    }).then(r => r.json()) as Promise<{ ok: boolean }>,
}

// ── Types matching Python Pydantic models ─────────────────────────────────────

export interface ECExecuteResponse {
  ec_id: string
  output: Record<string, unknown> | null
  success: boolean
  error: string | null
  latency_ms: number
}

export interface AgentInfo {
  agent_id: string
  queue_size: number
  queue_maxsize: number
}

export interface AgentQueryResponse {
  correlation_id: string
  agent_id: string
  response: string
}

export interface SnapshotPreviewRequest {
  agent_id: string
  profile_name?: string | null
  profile_override?: Record<string, unknown>
}

export interface SnapshotPreviewResponse {
  agent_id: string
  broker_name: string
  pair: string
  trigger_payload: Record<string, unknown>
  effective_profile: Record<string, unknown>
  snapshot: Record<string, unknown>
  validation_errors: string[]
  decision_input: string
}

export interface SnapshotToolPreviewRequest {
  agent_id: string
  tool_block: Record<string, unknown>
  pair_override?: string | null
  short_timeframe?: string
  long_timeframe?: string
}

export interface SnapshotToolPreviewResponse {
  agent_id: string
  broker_name: string
  pair: string
  runtime_context: Record<string, unknown>
  tool_block: Record<string, unknown>
  raw_output: unknown
  transformed_output: unknown
  errors: string[]
}

export type CalculationBlockType = 'script'

export interface CalculationBlock {
  id: string
  type: CalculationBlockType
  enabled: boolean
  sources: Record<string, string>
  config: Record<string, unknown>
  script?: string
}

export interface SnapshotCalculationPreviewRequest {
  agent_id: string
  calculation_block: Record<string, unknown>
  tool_results?: Record<string, unknown>
  pair_override?: string | null
  strategy_aggressiveness?: string
  short_timeframe?: string
  long_timeframe?: string
}

export interface SnapshotCalculationPreviewResponse {
  agent_id: string
  calculation_block: Record<string, unknown>
  result: unknown
  errors: string[]
}

export interface DecisionPromptScriptTestRequest {
  script: string
  snapshot: Record<string, unknown>
  prompts: Array<Record<string, unknown>>
}

export interface DecisionPromptScriptTestResponse {
  result: number | null
  placeholders: Record<string, unknown>
  matched_prompt: Record<string, unknown> | null
  resolved_prompt: string | null
  error: string | null
}

export interface AgentExecuteRequest {
  input_text?: string
  snapshot_profile_override?: Record<string, unknown>
  decision_prompt_profile_override?: Record<string, unknown>
}

export interface AgentExecuteResponse {
  run_id: string
  agent_id: string
  trigger: string
  source: string
  built_user_message: string
  final_response: string
  effective_system_prompt?: string | null
  total_tokens: number
  elapsed_ms: number
  snapshot?: Record<string, unknown> | null
  validation_errors: string[]
  events: MonitoringEvent[]
}

export interface ToolInfo {
  name: string
  description: string
  input_schema: JsonSchema
  requires_approval: boolean
}

export interface JsonSchema {
  type: string
  properties?: Record<string, JsonSchemaProperty>
  required?: string[]
}

export interface JsonSchemaProperty {
  type: string
  description?: string
  enum?: string[]
}

export interface ToolExecuteResponse {
  tool_name: string
  result: unknown
  is_error: boolean
}


export interface LlmCheckerMessage {
  role: 'user' | 'assistant' | 'tool' | 'system'
  content: unknown
}

export interface LlmCheckerRequest {
  llm_name: string
  messages: LlmCheckerMessage[]
  enabled_tools: string[]
  system_prompt?: string
  temperature?: number
  max_tokens?: number
  max_tool_turns?: number
  agent_id?: string | null
  broker_name?: string | null
  pair?: string | null
}

export interface LlmCheckerResponse {
  llm_name: string
  final_text: string
  total_tokens: number
  stop_reason: string
  trace: Array<Record<string, unknown>>
}
export interface MonitoringEvent {
  id: string
  timestamp: string
  source: string
  event_type: string
  broker: string | null
  pair: string | null
  payload: Record<string, unknown>
}

export interface PinnedMonitoringEvent extends MonitoringEvent {
  auto_pinned: boolean
}

export interface EventInjectRequest {
  event_type: string
  source_agent_id?: string
  target_agent_id?: string | null
  payload?: Record<string, unknown>
  correlation_id?: string | null
}

export interface CandleBar {
  timestamp: string
  open: number
  high: number
  low: number
  close: number
  tick_volume: number
  spread: number
}

export interface IndicatorValue {
  timestamp: string
  value: number
}

export interface MarketDataIndicator {
  indicator: string
  period: number
  timeframe: string
  latest: number
  direction: string
  values: IndicatorValue[]
}

export interface AnalysisIndicatorSnapshot {
  name: string
  timeframe: string
  value: number
  source?: string
}

export interface AnalysisLevelSnapshot {
  support?: number[]
  resistance?: number[]
  invalidation?: number[]
  target?: number[]
}

export interface AnalysisOverlaySnapshot {
  levels: AnalysisLevelSnapshot
  indicators: AnalysisIndicatorSnapshot[]
}

export interface OrderDecisionContext {
  symbol?: string | null
  decision?: string | null
  confidence?: number | null
  order_start_signal?: string | null
  entry_quality?: string | null
  setup_type?: string | null
  analysis_summary?: string | null
  conflict_flags?: string[]
}

export interface OrderbookEntrySummary {
  id: string
  broker_name: string
  broker_order_id?: string | null
  sync_key?: string | null
  agent_id: string
  pair: string
  direction: string
  order_type: string
  units: number
  requested_price: number
  fill_price?: number | null
  stop_loss?: number | null
  take_profit?: number | null
  status: string
  requested_at: string
  opened_at?: string | null
  close_requested_at?: string | null
  closed_at?: string | null
  signal_confidence: number
  entry_reasoning: string
  close_reason?: string | null
  close_price?: number | null
  close_reasoning?: string | null
  pnl_pips?: number | null
  pnl_account_currency?: number | null
  sync_confirmed: boolean
  confirmed_by_broker: boolean
  stake_estimate?: number | null
  decision_context: OrderDecisionContext
  analysis_overlays: AnalysisOverlaySnapshot
  analysis_available: boolean
}

export interface OrderbookEntryDetail extends OrderbookEntrySummary {
  analysis_text?: string | null
  analysis?: Record<string, unknown> | null
  market_context_snapshot: Record<string, unknown>
}

export interface AnalysisRecord {
  id: string
  agent_id: string
  pair?: string | null
  decision_type?: string | null
  decided_at: string
  llm_model: string
  tokens_used: number
  latency_ms?: number | null
  analysis_text?: string | null
  analysis?: Record<string, unknown> | null
  decision?: string | null
  confidence?: number | null
  order_start_signal?: string | null
  entry_quality?: string | null
  setup_type?: string | null
  bus_payload: Record<string, unknown>
  input_context: Record<string, unknown>
  output: Record<string, unknown>
  market_snapshot: Record<string, unknown>
}








// ── Prompt Library ────────────────────────────────────────────────────────────

export interface PromptLibraryEntry {
  id: string
  name: string
  version: string
  description: string
  text: string
  [key: string]: unknown  // extensible for future fields
}

export interface PromptLibrary {
  prompts: PromptLibraryEntry[]
}

// ── Snippet Library ────────────────────────────────────────────────────────────

export interface SnippetLibraryEntry {
  id: string
  name: string
  version: string
  description: string
  tags: string
  code: string
  [key: string]: unknown  // extensible for future fields
}

export interface SnippetLibrary {
  snippets: SnippetLibraryEntry[]
}

// ── LLM Assistant ─────────────────────────────────────────────────────────────

export interface LLMAssistantMessage {
  role: 'user' | 'assistant'
  content: string
}

export interface LLMAssistantChatRequest {
  context_file: string
  script: string
  question: string
  history: LLMAssistantMessage[]
}

export interface LLMAssistantChatResponse {
  answer: string
  error?: string
}

export interface PackageMapping {
  broker_map?: Record<string, string>
  llm_map?: Record<string, string>
  agent_id_map?: Record<string, string>
  agent_id_prefix?: string
}

export interface PackageExportRequest {
  include_agents?: boolean
  agent_ids?: string[]
  include_snapshot_profiles?: boolean
  include_decision_prompt_profiles?: boolean
  include_bridge_tools?: boolean
  include_event_routing?: boolean
  include_system_config?: boolean
  strict_dependencies?: boolean
}

export interface PackageValidateRequest {
  content: string
  mapping?: PackageMapping
  replace_existing_agents?: boolean
}

export interface PackageImportRequest {
  content: string
  mapping?: PackageMapping
  replace_existing_agents?: boolean
  import_agents?: boolean
  import_snapshot_profiles?: boolean
  import_decision_prompt_profiles?: boolean
  import_bridge_tools?: boolean
  import_event_routing?: boolean
  import_system_config?: boolean
}

export interface PackageProblem {
  level: 'error' | 'warning' | string
  path: string
  message: string
}

export interface PackageValidationResponse {
  ok: boolean
  problems: PackageProblem[]
  preview?: Record<string, unknown>
  status?: string
}

export interface PackageExportResponse {
  package: Record<string, unknown>
  text: string
}

export interface PackageImportResponse {
  status: string
  runtime_apply?: Record<string, unknown>
  validation?: PackageValidationResponse
  ok?: boolean
  problems?: PackageProblem[]
}




export interface InitialConsoleModuleItem {
  name: string
  status: 'connected' | 'missing' | string
  short_name?: string | null
}

export interface InitialConsoleAgentItem {
  agent_id: string
  enabled: boolean
  type?: string | null
  pair?: string | null
  broker?: string | null
  llm?: string | null
  snapshot_profile?: string | null
  decision_prompt_profile?: string | null
  session_active: boolean
  task: string
  comment?: string | null
  last_error?: { timestamp: string; event_type: string; message: string } | null
  last_active_at?: string | null
}

export interface InitialConsoleComposerItem {
  ec_id: string
  enabled: boolean
  broker?: string | null
  pair?: string | null
  triggers: string[]
  comment?: string | null
}

export interface InitialConsoleResponse {
  logo: string[]
  llm: {
    configured_count: number
    connected_count: number
    items: InitialConsoleModuleItem[]
  }
  broker: {
    configured_count: number
    connected_count: number
    items: InitialConsoleModuleItem[]
  }
  agents: {
    configured_count: number
    enabled_count: number
    items: InitialConsoleAgentItem[]
  }
  event_composers: {
    configured_count: number
    enabled_count: number
    items: InitialConsoleComposerItem[]
  }
  version: {
    local: string
    remote: string | null
    remote_prerelease: boolean | null
    remote_published_at: string | null
    remote_url: string | null
    remote_error: string | null
  }
  timestamp: string
}


export interface SystemUpdateStartRequest {
  version?: string | null
}

export interface SystemUpdateStatusResponse {
  state: 'idle' | 'running' | 'completed' | 'failed' | string
  started_at?: string | null
  ended_at?: string | null
  exit_code?: number | null
  message?: string
  requested_version?: string | null
  restart_supported?: boolean
  restart_available?: boolean
  runtime_paused?: boolean
  output: string[]
}

// ── Knowledge base types ───────────────────────────────────────────────────────

export interface KbDocMeta {
  id: string
  title: string
  is_folder: number
  parent_id: string | null
  sort_order: number
  tags: string
  created_at: string
  updated_at: string
}

export interface KbDoc extends KbDocMeta {
  content: string
}

export interface KbSearchResult {
  doc_id: string
  title: string
  snippet: string
}
