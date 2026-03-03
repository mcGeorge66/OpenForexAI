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

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(`POST ${path} → ${res.status}: ${text}`)
  }
  return res.json() as Promise<T>
}

// ── Exported API calls ────────────────────────────────────────────────────────

export const api = {
  getVersion:     () => get<{ version: string }>('/version'),
  getHealth:      () => get<{ status: string; uptime_seconds: number; registered_agents: number }>('/health'),
  getRuntimeStatus: () => get<{ agents: string[]; routing_rules: number; uptime_seconds: number }>('/runtime/status'),
  getAgents:      () => get<AgentInfo[]>('/agents'),
  askAgent:       (agentId: string, question: string, timeout = 120) =>
                    post<AgentQueryResponse>(`/agents/${encodeURIComponent(agentId)}/ask`, { question, timeout }),
  getTools:       () => get<{ tools: ToolInfo[] }>('/tools'),
  executeTool:    (tool_name: string, arguments_: Record<string, unknown>) =>
                    post<ToolExecuteResponse>('/tools/execute', { tool_name, arguments: arguments_ }),
  getConfigView:  () => get<Record<string, unknown>>('/config/view'),
  getConfigFile:  (name: string) => get<Record<string, unknown>>(`/config/files/${name}`),
  injectEvent:    (body: EventInjectRequest) => post<{ message_id: string }>('/events', body),
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
