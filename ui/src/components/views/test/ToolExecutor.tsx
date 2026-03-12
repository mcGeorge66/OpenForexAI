/**
 * ToolExecutor — select a registered tool, fill its arguments, execute it,
 * and inspect the result.  Uses GET /tools for the manifest and POST /tools/execute.
 */

import { useEffect, useMemo, useState } from 'react'
import { api, type ToolInfo, type JsonSchemaProperty } from '@/api/client'
import { useTools } from '@/hooks/useTools'
import { Play, ChevronDown, ChevronRight } from 'lucide-react'

function highlight(json: string): string {
  return json
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(
      /("(\\u[a-zA-Z0-9]{4}|\\[^u]|[^\\"])*"(\s*:)?|\b(true|false|null)\b|-?\d+(?:\.\d*)?(?:[eE][+\-]?\d+)?)/g,
      match => {
        if (/^"/.test(match)) {
          if (/:$/.test(match)) return `<span style="color:#7dd3fc">${match}</span>`
          return `<span style="color:#86efac">${match}</span>`
        }
        if (/true|false/.test(match)) return `<span style="color:#fbbf24">${match}</span>`
        if (/null/.test(match)) return `<span style="color:#9ca3af">${match}</span>`
        return `<span style="color:#c4b5fd">${match}</span>`
      },
    )
}

/** Render a dynamic form from a JSON schema */
function SchemaForm({
  schema,
  values,
  onChange,
}: {
  schema: ToolInfo['input_schema']
  values: Record<string, string>
  onChange: (key: string, value: string) => void
}) {
  const props = schema.properties ?? {}
  const required = new Set(schema.required ?? [])
  const entries = Object.entries(props) as [string, JsonSchemaProperty][]

  if (entries.length === 0) {
    return <p className="text-gray-500 text-xs italic">No arguments required.</p>
  }

  return (
    <div className="space-y-3">
      {entries.map(([key, prop]) => (
        <div key={key}>
          <label className="block text-xs text-gray-400 mb-1">
            <span className="text-blue-300">{key}</span>
            {required.has(key) && <span className="text-red-400 ml-1">*</span>}
            {prop.type && (
              <span className="text-gray-600 ml-1">({prop.type})</span>
            )}
          </label>
          {prop.description && (
            <p className="text-xs text-gray-600 mb-1">{prop.description}</p>
          )}
          {prop.enum ? (
            <select
              value={values[key] ?? ''}
              onChange={e => onChange(key, e.target.value)}
              className="w-full bg-gray-800 text-gray-200 text-sm rounded px-2 py-1.5 border border-gray-600 focus:outline-none focus:border-emerald-500"
            >
              <option value="">— select —</option>
              {prop.enum.map(opt => (
                <option key={opt} value={opt}>{opt}</option>
              ))}
            </select>
          ) : (
            <input
              type={prop.type === 'integer' || prop.type === 'number' ? 'number' : 'text'}
              value={values[key] ?? ''}
              onChange={e => onChange(key, e.target.value)}
              placeholder={prop.description ?? key}
              className="w-full bg-gray-800 text-gray-200 text-sm rounded px-2 py-1.5 border border-gray-600 focus:outline-none focus:border-emerald-500 font-mono"
            />
          )}
        </div>
      ))}
    </div>
  )
}

function coerceArguments(
  values: Record<string, string>,
  schema: ToolInfo['input_schema'],
): Record<string, unknown> {
  const props = schema.properties ?? {}
  const result: Record<string, unknown> = {}
  for (const [key, raw] of Object.entries(values)) {
    if (raw === '') continue
    const prop = props[key]
    if (prop?.type === 'integer') {
      result[key] = parseInt(raw, 10)
    } else if (prop?.type === 'number') {
      result[key] = parseFloat(raw)
    } else if (prop?.type === 'boolean') {
      result[key] = raw === 'true'
    } else {
      result[key] = raw
    }
  }
  return result
}

type BrokerOption = {
  value: string
  label: string
}

export function ToolExecutor() {
  const { tools, loading: toolsLoading } = useTools()
  const [selectedTool, setSelectedTool] = useState<string>('')
  const [values, setValues] = useState<Record<string, string>>({})
  const [agentOptions, setAgentOptions] = useState<string[]>([])
  const [pairOptions, setPairOptions] = useState<string[]>([])
  const [brokerOptions, setBrokerOptions] = useState<BrokerOption[]>([])
  const [llmOptions, setLlmOptions] = useState<string[]>([])
  const [agentId, setAgentId] = useState<string>('')
  const [brokerName, setBrokerName] = useState<string>('')
  const [llmName, setLlmName] = useState<string>('')
  const [pair, setPair] = useState<string>('')
  const [contextError, setContextError] = useState<string | null>(null)
  const [running, setRunning] = useState(false)
  const [result, setResult] = useState<unknown>(null)
  const [isError, setIsError] = useState(false)
  const [schemaOpen, setSchemaOpen] = useState(false)

  useEffect(() => {
    api.getAgents()
       .then(resp => {
        const ids = resp.map(a => a.agent_id)
        setAgentOptions(ids)
        const pairs = Array.from(new Set(
          ids
            .map(id => id.split('-')[1]?.trim().toUpperCase() ?? '')
            .filter(p => p && p !== 'ALL___'),
        )).sort()
        setPairOptions(pairs)
      })
      .catch(err => setContextError(String(err)))
    api.getModuleNames('broker')
      .then(async resp => {
        const rows = await Promise.all(resp.names.map(async moduleName => {
          try {
            const cfg = await api.getModuleConfig('broker', moduleName)
            const configured = typeof cfg.short_name === 'string' ? cfg.short_name.trim() : ''
            const shortName = configured || moduleName
            return {
              value: shortName,
              label: `${shortName} (${moduleName})`,
            }
          } catch {
            return {
              value: moduleName,
              label: moduleName,
            }
          }
        }))
        rows.sort((a, b) => a.label.localeCompare(b.label))
        setBrokerOptions(rows)
      })
      .catch(err => setContextError(String(err)))
    api.getModuleNames('llm')
      .then(resp => setLlmOptions(resp.names))
      .catch(err => setContextError(String(err)))
  }, [])

  const tool = tools.find(t => t.name === selectedTool)
  const isPlaceOrder = tool?.name === 'place_order'

  useEffect(() => {
    if (!tool) return
    const hasAgentArg = Boolean(tool.input_schema.properties?.agent)
    if (!hasAgentArg) return
    const nextAgent = agentId.trim()
    setValues(prev => {
      if ((prev.agent ?? '') === nextAgent) return prev
      return { ...prev, agent: nextAgent }
    })
  }, [agentId, tool])
  useEffect(() => {
    if (!agentId) return
    const parts = agentId.split('-')
    const fromId = (parts[1] ?? '').trim().toUpperCase()
    if (fromId && fromId !== 'ALL___') setPair(fromId)
  }, [agentId])

  const placeOrderIssues = useMemo(() => {
    if (!isPlaceOrder) return [] as string[]
    const issues: string[] = []
    const orderType = (values.order_type || '').toUpperCase()
    const units = Number(values.units)
    if (!brokerName && !agentId) {
      issues.push('Select a Broker (short name) or an Agent context for realistic execution tests.')
    }
    if (!values.direction) issues.push('direction is required.')
    if (!orderType) issues.push('order_type is required.')
    if (!values.units) {
      issues.push('units is required.')
    } else if (!Number.isFinite(units) || units <= 0 || !Number.isInteger(units)) {
      issues.push('units must be a positive integer.')
    }
    if (orderType === 'LIMIT' && !values.limit_price) issues.push('LIMIT requires limit_price.')
    if (orderType === 'STOP' && !values.stop_price) issues.push('STOP requires stop_price.')
    if (orderType === 'STOP_LIMIT') {
      if (!values.stop_price) issues.push('STOP_LIMIT requires stop_price.')
      if (!values.limit_price) issues.push('STOP_LIMIT requires limit_price.')
    }
    if (orderType === 'TRAILING_STOP' && !values.trailing_stop_distance) {
      issues.push('TRAILING_STOP requires trailing_stop_distance.')
    }
    return issues
  }, [isPlaceOrder, values, brokerName, agentId])

  const handleToolChange = (name: string) => {
    setSelectedTool(name)
    setValues({})
    setResult(null)
    setIsError(false)
  }

  const handleChange = (key: string, value: string) => {
    setValues(prev => ({ ...prev, [key]: value }))
  }

  const applyPlaceOrderPreset = (preset: 'MARKET' | 'LIMIT' | 'STOP' | 'STOP_LIMIT') => {
    const base: Record<string, string> = {
      direction: 'buy',
      order_type: preset,
      units: '10000',
      risk_pct: '1.0',
      confidence: '0.6',
      reasoning: 'ToolExecutor smoke test',
      entry_price: '1.10000',
      stop_loss: '1.09850',
      take_profit: '1.10200',
      limit_price: '',
      stop_price: '',
      trailing_stop_distance: '',
    }
    if (preset === 'LIMIT') base.limit_price = '1.09950'
    if (preset === 'STOP') base.stop_price = '1.10050'
    if (preset === 'STOP_LIMIT') {
      base.stop_price = '1.10050'
      base.limit_price = '1.10070'
    }
    setValues(base)
    setResult(null)
    setIsError(false)
  }

  const execute = async () => {
    if (!tool || running) return
    setRunning(true)
    setResult(null)
    try {
      const args = coerceArguments(values, tool.input_schema)
      const resp = await api.executeTool(
        tool.name,
        args,
        agentId.trim() || null,
        brokerName.trim() || null,
        llmName.trim() || null,
        pair.trim() ? pair.trim().toUpperCase() : null,
      )
      setResult(resp.result)
      setIsError(resp.is_error)
    } catch (err) {
      setResult({ error: String(err) })
      setIsError(true)
    } finally {
      setRunning(false)
    }
  }

  const resultJson = result !== null ? JSON.stringify(result, null, 2) : null

  return (
    <div className="flex flex-col h-full overflow-hidden">
      <div className="flex-1 min-h-0 p-4 flex flex-col gap-4 overflow-hidden">
        {/* Tool selector */}
        <div>
          <label className="block text-xs text-gray-400 mb-1">Tool</label>
          <select
            value={selectedTool}
            onChange={e => handleToolChange(e.target.value)}
            disabled={toolsLoading}
            className="w-full max-w-sm bg-gray-800 text-gray-200 text-sm rounded px-2 py-1.5 border border-gray-600 focus:outline-none focus:border-emerald-500"
          >
            <option value="">— select tool —</option>
            {tools.map(t => (
              <option key={t.name} value={t.name}>{t.name}</option>
            ))}
          </select>
        </div>

        {/* Context: agent + broker + llm + pair */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
          <div className="flex-1">
            <label className="block text-xs text-gray-400 mb-1">
              Agent
              <span className="text-gray-600 ml-1">(optional)</span>
            </label>
            <select
              value={agentId}
              onChange={e => setAgentId(e.target.value)}
              className="w-full bg-gray-800 text-gray-200 text-sm rounded px-2 py-1.5 border border-gray-600 focus:outline-none focus:border-emerald-500 font-mono"
            >
              <option value="">— none —</option>
              {agentOptions.map(id => (
                <option key={id} value={id}>{id}</option>
              ))}
            </select>
          </div>
          <div className="flex-1">
            <label className="block text-xs text-gray-400 mb-1">
              Broker
              <span className="text-gray-600 ml-1">(optional)</span>
            </label>
            <select
              value={brokerName}
              onChange={e => setBrokerName(e.target.value)}
              className="w-full bg-gray-800 text-gray-200 text-sm rounded px-2 py-1.5 border border-gray-600 focus:outline-none focus:border-emerald-500 font-mono"
            >
              <option value="">— none —</option>
              {brokerOptions.map(opt => (
                <option key={opt.label} value={opt.value}>{opt.label}</option>
              ))}
            </select>
          </div>
          <div className="flex-1">
            <label className="block text-xs text-gray-400 mb-1">
              LLM
              <span className="text-gray-600 ml-1">(optional)</span>
            </label>
            <select
              value={llmName}
              onChange={e => setLlmName(e.target.value)}
              className="w-full bg-gray-800 text-gray-200 text-sm rounded px-2 py-1.5 border border-gray-600 focus:outline-none focus:border-emerald-500 font-mono"
            >
              <option value="">— none —</option>
              {llmOptions.map(name => (
                <option key={name} value={name}>{name}</option>
              ))}
            </select>
          </div>
          <div className="flex-1">
            <label className="block text-xs text-gray-400 mb-1">
              Pair
              <span className="text-gray-600 ml-1">(optional)</span>
            </label>
            <input
              list="tool-exec-pair-options"
              value={pair}
              onChange={e => setPair(e.target.value.toUpperCase())}
              placeholder="EURUSD"
              className="w-full bg-gray-800 text-gray-200 text-sm rounded px-2 py-1.5 border border-gray-600 focus:outline-none focus:border-emerald-500 font-mono"
            />
            <datalist id="tool-exec-pair-options">
              {pairOptions.map(p => (
                <option key={p} value={p} />
              ))}
            </datalist>
          </div>
        </div>
        {contextError && (
          <p className="text-red-400 text-xs">Error loading context options: {contextError}</p>
        )}

        {tool && (
          <div className="flex flex-col gap-4 flex-1 min-h-0">
            {/* Tool description */}
            <div className="bg-gray-900 rounded p-3 border border-gray-700">
              <p className="text-sm leading-6 text-gray-200">{tool.description}</p>
              {tool.requires_approval && (
                <p className="text-xs text-orange-400 mt-1">⚠ This tool requires approval</p>
              )}
            </div>

            {/* Raw schema toggle */}
            <div>
              <button
                onClick={() => setSchemaOpen(v => !v)}
                className="flex items-center gap-1 text-xs text-gray-500 hover:text-gray-300 transition-colors"
              >
                {schemaOpen
                  ? <ChevronDown className="w-3 h-3" />
                  : <ChevronRight className="w-3 h-3" />}
                Input schema
              </button>
              {schemaOpen && (
                <pre
                  className="mt-2 text-xs font-mono bg-gray-900 p-3 rounded border border-gray-700 overflow-auto max-h-48"
                  dangerouslySetInnerHTML={{
                    __html: highlight(JSON.stringify(tool.input_schema, null, 2)),
                  }}
                />
              )}
            </div>

            <hr className="border-gray-700" />

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 flex-1 min-h-0 items-stretch">
              {/* Arguments form */}
              <div className="flex flex-col min-h-0">
                <div className="flex items-center justify-between mb-2">
                  <h3 className="text-xs font-semibold text-gray-300 uppercase tracking-wider">
                    Arguments
                  </h3>
                  <button
                    onClick={execute}
                    disabled={running}
                    className="flex items-center gap-2 px-3 py-1.5 bg-emerald-700 hover:bg-emerald-600 disabled:bg-gray-700 disabled:text-gray-500 text-white text-xs rounded transition-colors"
                  >
                    <Play className="w-3.5 h-3.5" />
                    {running ? 'Executing…' : 'Execute'}
                  </button>
                </div>
                <div className="flex-1 min-h-0 overflow-auto pr-1">
                  {isPlaceOrder && (
                    <div className="mb-3 p-2 border border-gray-700 rounded bg-gray-900/50 space-y-2">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="text-[11px] text-gray-400 uppercase tracking-wide">Quick presets:</span>
                        <button onClick={() => applyPlaceOrderPreset('MARKET')} className="text-xs px-2 py-1 rounded bg-gray-800 border border-gray-600 text-gray-200 hover:bg-gray-700">Market</button>
                        <button onClick={() => applyPlaceOrderPreset('LIMIT')} className="text-xs px-2 py-1 rounded bg-gray-800 border border-gray-600 text-gray-200 hover:bg-gray-700">Limit</button>
                        <button onClick={() => applyPlaceOrderPreset('STOP')} className="text-xs px-2 py-1 rounded bg-gray-800 border border-gray-600 text-gray-200 hover:bg-gray-700">Stop</button>
                        <button onClick={() => applyPlaceOrderPreset('STOP_LIMIT')} className="text-xs px-2 py-1 rounded bg-gray-800 border border-gray-600 text-gray-200 hover:bg-gray-700">Stop-Limit</button>
                      </div>
                      {placeOrderIssues.length > 0 ? (
                        <ul className="text-xs text-amber-300 space-y-1">
                          {placeOrderIssues.map(issue => <li key={issue}>- {issue}</li>)}
                        </ul>
                      ) : (
                        <p className="text-xs text-emerald-400">Smoke-check OK: required place_order fields are present.</p>
                      )}
                    </div>
                  )}
                  <SchemaForm
                    schema={tool.input_schema}
                    values={values}
                    onChange={handleChange}
                  />
                </div>
              </div>

              {/* Result */}
              <div className="flex flex-col min-h-0 h-full">
                <h3 className={`text-xs font-semibold uppercase tracking-wider mb-2 ${
                  isError ? 'text-red-400' : 'text-emerald-400'
                }`}>
                  {isError ? 'Error' : 'Result'}
                </h3>
                {resultJson === null ? (
                  <div className="text-xs text-gray-500 border border-gray-700 rounded p-3 bg-gray-900 flex-1 overflow-auto">
                    No result yet.
                  </div>
                ) : (
                  <pre
                    className={`text-xs font-mono p-3 rounded border overflow-auto flex-1 ${
                      isError
                        ? 'bg-red-950/30 border-red-800'
                        : 'bg-gray-900 border-gray-700'
                    }`}
                    dangerouslySetInnerHTML={{ __html: highlight(resultJson) }}
                  />
                )}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}















