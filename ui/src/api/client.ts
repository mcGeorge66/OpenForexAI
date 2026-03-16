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
  getAgents:      () => get<AgentInfo[]>('/agents'),
  askAgent:       (agentId: string, question: string, timeout = 120) =>
                    post<AgentQueryResponse>(`/agents/${encodeURIComponent(agentId)}/ask`, { question, timeout }),
  getAgentCandles: (agentId: string, timeframe = 'M5', count = 100) =>
                    get<CandleBar[]>(
                      `/agents/${encodeURIComponent(agentId)}/candles?timeframe=${encodeURIComponent(timeframe)}&count=${count}`,
                    ),
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
  runLlmChecker: (body: LlmCheckerRequest) => post<LlmCheckerResponse>('/test/llm/check', body),
  getConfigView:   () => get<Record<string, unknown>>('/config/view'),
  getProjectReadmeText: () => getText('/config/information/readme'),
  saveProjectReadmeText: (content: string) =>
                    put<{ status: string; file: string }>('/config/information/readme', content),
  getSystemConfig: () => get<Record<string, unknown>>('/config/system'),
  getSystemConfigText: () => getText('/config/system/text'),
  saveSystemConfig: (content: Record<string, unknown> | string) =>
                    put<{ status: string; file: string }>('/config/system', content),
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
}

// ── Types matching Python Pydantic models ─────────────────────────────────────

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








export interface PackageMapping {
  broker_map?: Record<string, string>
  llm_map?: Record<string, string>
  agent_id_map?: Record<string, string>
  agent_id_prefix?: string
}

export interface PackageExportRequest {
  agent_ids?: string[]
  include_routing?: boolean
  include_agent_tools?: boolean
  include_modules_snapshot?: boolean
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
  import_routing?: boolean
  import_agent_tools?: boolean
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
  task: string
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
