/**
 * ToolExecutor — select a registered tool, fill its arguments, execute it,
 * and inspect the result.  Uses GET /tools for the manifest and POST /tools/execute.
 */

import { useState } from 'react'
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

export function ToolExecutor() {
  const { tools, loading: toolsLoading } = useTools()
  const [selectedTool, setSelectedTool] = useState<string>('')
  const [values, setValues] = useState<Record<string, string>>({})
  const [running, setRunning] = useState(false)
  const [result, setResult] = useState<unknown>(null)
  const [isError, setIsError] = useState(false)
  const [schemaOpen, setSchemaOpen] = useState(false)

  const tool = tools.find(t => t.name === selectedTool)

  const handleToolChange = (name: string) => {
    setSelectedTool(name)
    setValues({})
    setResult(null)
    setIsError(false)
  }

  const handleChange = (key: string, value: string) => {
    setValues(prev => ({ ...prev, [key]: value }))
  }

  const execute = async () => {
    if (!tool || running) return
    setRunning(true)
    setResult(null)
    try {
      const args = coerceArguments(values, tool.input_schema)
      const resp = await api.executeTool(tool.name, args)
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
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
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

        {tool && (
          <>
            {/* Tool description */}
            <div className="bg-gray-900 rounded p-3 border border-gray-700">
              <p className="text-xs text-gray-300">{tool.description}</p>
              {tool.requires_approval && (
                <p className="text-xs text-orange-400 mt-1">⚠ This tool requires approval</p>
              )}
            </div>

            {/* Arguments form */}
            <div>
              <h3 className="text-xs font-semibold text-gray-300 mb-2 uppercase tracking-wider">
                Arguments
              </h3>
              <SchemaForm
                schema={tool.input_schema}
                values={values}
                onChange={handleChange}
              />
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

            {/* Execute button */}
            <button
              onClick={execute}
              disabled={running}
              className="flex items-center gap-2 px-4 py-2 bg-emerald-700 hover:bg-emerald-600 disabled:bg-gray-700 disabled:text-gray-500 text-white text-sm rounded transition-colors"
            >
              <Play className="w-4 h-4" />
              {running ? 'Executing…' : 'Execute'}
            </button>
          </>
        )}

        {/* Result */}
        {resultJson !== null && (
          <div>
            <h3 className={`text-xs font-semibold uppercase tracking-wider mb-2 ${
              isError ? 'text-red-400' : 'text-emerald-400'
            }`}>
              {isError ? 'Error' : 'Result'}
            </h3>
            <pre
              className={`text-xs font-mono p-3 rounded border overflow-auto max-h-80 ${
                isError
                  ? 'bg-red-950/30 border-red-800'
                  : 'bg-gray-900 border-gray-700'
              }`}
              dangerouslySetInnerHTML={{ __html: highlight(resultJson) }}
            />
          </div>
        )}
      </div>
    </div>
  )
}
