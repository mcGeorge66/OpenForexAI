import { useEffect, useMemo, useRef, useState } from 'react'
import {
  api,
  type PackageImportResponse,
  type PackageMapping,
  type PackageValidationResponse,
} from '@/api/client'

type AgentMap = Record<string, Record<string, unknown>>

function parseMapLines(text: string): Record<string, string> {
  const out: Record<string, string> = {}
  for (const raw of text.split('\n')) {
    const line = raw.trim()
    if (!line || line.startsWith('#') || line.startsWith('//')) continue
    const idx = line.indexOf('=')
    if (idx <= 0) continue
    const oldKey = line.slice(0, idx).trim()
    const newVal = line.slice(idx + 1).trim()
    if (oldKey && newVal) out[oldKey] = newVal
  }
  return out
}

function downloadText(filename: string, text: string): void {
  const blob = new Blob([text], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

export function PackageManager() {
  const [agents, setAgents] = useState<string[]>([])
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [packageText, setPackageText] = useState('')
  const [includeRouting, setIncludeRouting] = useState(true)
  const [includeAgentTools, setIncludeAgentTools] = useState(true)
  const [includeModules, setIncludeModules] = useState(true)
  const [strictDependencies, setStrictDependencies] = useState(false)
  const [replaceExisting, setReplaceExisting] = useState(false)
  const [importRouting, setImportRouting] = useState(true)
  const [importAgentTools, setImportAgentTools] = useState(true)
  const [agentPrefix, setAgentPrefix] = useState('')
  const [brokerMapText, setBrokerMapText] = useState('')
  const [llmMapText, setLlmMapText] = useState('')
  const [agentIdMapText, setAgentIdMapText] = useState('')
  const [loading, setLoading] = useState(false)
  const [dragOver, setDragOver] = useState(false)
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [validation, setValidation] = useState<PackageValidationResponse | null>(null)
  const fileInputRef = useRef<HTMLInputElement | null>(null)

  const selectedList = useMemo(() => Array.from(selected).sort(), [selected])

  const mapping: PackageMapping = useMemo(() => ({
    agent_id_prefix: agentPrefix.trim().toUpperCase(),
    broker_map: parseMapLines(brokerMapText),
    llm_map: parseMapLines(llmMapText),
    agent_id_map: parseMapLines(agentIdMapText),
  }), [agentPrefix, brokerMapText, llmMapText, agentIdMapText])

  useEffect(() => {
    api.getSystemConfig()
      .then(cfg => {
        const a = (cfg.agents ?? {}) as AgentMap
        const ids = Object.keys(a).sort()
        setAgents(ids)
        setSelected(new Set(ids))
      })
      .catch(err => setError(String(err)))
  }, [])

  const toggleAgent = (id: string) => {
    setSelected(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const loadPackageFile = async (file: File) => {
    try {
      const text = await file.text()
      setPackageText(text)
      setValidation(null)
      setMessage(`Loaded package file: ${file.name}`)
      setError(null)
    } catch (err) {
      setError(`Failed to read file: ${String(err)}`)
    }
  }

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) await loadPackageFile(file)
    e.target.value = ''
  }

  const handleDrop = async (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    setDragOver(false)
    const file = e.dataTransfer.files?.[0]
    if (file) await loadPackageFile(file)
  }

  const doExport = async () => {
    setLoading(true)
    setError(null)
    setMessage(null)
    try {
      const resp = await api.exportAgentPackage({
        agent_ids: selectedList,
        include_routing: includeRouting,
        include_agent_tools: includeAgentTools,
        include_modules_snapshot: includeModules,
        strict_dependencies: strictDependencies,
      })
      setPackageText(resp.text)
      const ts = new Date().toISOString().replace(/[:.]/g, '-')
      downloadText(`ofai-agent-package-${ts}.json5`, resp.text)

      const meta = (resp.package?.meta ?? {}) as Record<string, unknown>
      const issues = Array.isArray(meta.dependency_issues) ? meta.dependency_issues.length : 0
      const strictOk = meta.strict_ok !== false
      setMessage(
        strictDependencies
          ? `Exported ${selectedList.length} agents. Strict check: ${strictOk ? 'OK' : 'issues found'} (${issues}).`
          : `Exported ${selectedList.length} agents.`,
      )
    } catch (err) {
      setError(String(err))
    } finally {
      setLoading(false)
    }
  }

  const doValidate = async () => {
    if (!packageText.trim()) {
      setError('No package content to validate.')
      return
    }
    setLoading(true)
    setError(null)
    setMessage(null)
    try {
      const resp = await api.validateAgentPackage({
        content: packageText,
        mapping,
        replace_existing_agents: replaceExisting,
      })
      setValidation(resp)
      setMessage(resp.ok ? 'Validation successful.' : 'Validation found issues.')
    } catch (err) {
      setError(String(err))
    } finally {
      setLoading(false)
    }
  }

  const doImport = async () => {
    if (!packageText.trim()) {
      setError('No package content to import.')
      return
    }
    setLoading(true)
    setError(null)
    setMessage(null)
    try {
      const resp: PackageImportResponse = await api.importAgentPackage({
        content: packageText,
        mapping,
        replace_existing_agents: replaceExisting,
        import_routing: importRouting,
        import_agent_tools: importAgentTools,
      })
      if (resp.status === 'invalid') {
        setValidation({
          ok: Boolean(resp.ok),
          problems: resp.problems ?? [],
        })
        setError('Import rejected: validation failed.')
      } else {
        setMessage('Package imported successfully.')
        setValidation(resp.validation ?? null)
      }
    } catch (err) {
      setError(String(err))
    } finally {
      setLoading(false)
    }
  }

  const allSelected = agents.length > 0 && selected.size === agents.length

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between px-4 py-2 bg-gray-900 border-b border-gray-700 flex-shrink-0">
        <span className="text-sm text-gray-300 font-medium">Package Manager</span>
        <span className="text-xs text-gray-500">Portable agent bundles (agents + routing + tool policy)</span>
      </div>

      <div className="flex-1 min-h-0 p-4 bg-gray-950 overflow-auto space-y-4">
        {error && <p className="text-sm text-red-400">Error: {error}</p>}
        {message && <p className="text-sm text-emerald-400">{message}</p>}

        <section className="border border-gray-700 rounded p-3 bg-gray-900/40 space-y-3">
          <h3 className="text-sm text-gray-200 font-medium">Export</h3>
          <div className="flex items-center gap-3 text-xs text-gray-300">
            <label className="inline-flex items-center gap-2"><input type="checkbox" checked={includeRouting} onChange={e => setIncludeRouting(e.target.checked)} />Include Event Routing</label>
            <label className="inline-flex items-center gap-2"><input type="checkbox" checked={includeAgentTools} onChange={e => setIncludeAgentTools(e.target.checked)} />Include Agent Tools</label>
            <label className="inline-flex items-center gap-2"><input type="checkbox" checked={includeModules} onChange={e => setIncludeModules(e.target.checked)} />Include Modules Snapshot</label>
            <label className="inline-flex items-center gap-2"><input type="checkbox" checked={strictDependencies} onChange={e => setStrictDependencies(e.target.checked)} />Strict dependencies</label>
            <button
              onClick={doExport}
              disabled={loading || selected.size === 0}
              className="ml-auto text-xs px-3 py-1.5 rounded bg-emerald-700 hover:bg-emerald-600 text-white disabled:opacity-50"
            >
              Export Selected
            </button>
          </div>

          <div className="border border-gray-700 rounded max-h-48 overflow-y-auto p-2 bg-gray-950/60">
            <div className="flex items-center gap-2 mb-2">
              <button
                className="text-xs px-2 py-1 rounded border border-gray-700 text-gray-300 hover:bg-gray-800"
                onClick={() => setSelected(new Set(agents))}
              >
                Select all
              </button>
              <button
                className="text-xs px-2 py-1 rounded border border-gray-700 text-gray-300 hover:bg-gray-800"
                onClick={() => setSelected(new Set())}
              >
                Clear
              </button>
              <span className="text-xs text-gray-500">{allSelected ? 'All agents selected' : `${selected.size}/${agents.length} selected`}</span>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-1">
              {agents.map(id => (
                <label key={id} className="inline-flex items-center gap-2 text-xs text-gray-300">
                  <input type="checkbox" checked={selected.has(id)} onChange={() => toggleAgent(id)} />
                  <span>{id}</span>
                </label>
              ))}
            </div>
          </div>
        </section>

        <section className="border border-gray-700 rounded p-3 bg-gray-900/40 space-y-3">
          <h3 className="text-sm text-gray-200 font-medium">Mapping & Import Options</h3>
          <div className="grid grid-cols-1 lg:grid-cols-4 gap-3">
            <label className="text-xs text-gray-300">Agent ID Prefix
              <input
                value={agentPrefix}
                onChange={e => setAgentPrefix(e.target.value)}
                placeholder="e.g. DEMO-"
                className="mt-1 w-full bg-gray-800 border border-gray-600 rounded px-2 py-1 text-sm text-gray-200"
              />
            </label>
            <label className="text-xs text-gray-300">Broker Mapping (old=new)
              <textarea
                rows={5}
                value={brokerMapText}
                onChange={e => setBrokerMapText(e.target.value)}
                className="mt-1 w-full bg-gray-800 border border-gray-600 rounded px-2 py-1 text-xs font-mono text-gray-200"
              />
            </label>
            <label className="text-xs text-gray-300">LLM Mapping (old=new)
              <textarea
                rows={5}
                value={llmMapText}
                onChange={e => setLlmMapText(e.target.value)}
                className="mt-1 w-full bg-gray-800 border border-gray-600 rounded px-2 py-1 text-xs font-mono text-gray-200"
              />
            </label>
            <label className="text-xs text-gray-300">Agent ID Mapping (old=new)
              <textarea
                rows={5}
                value={agentIdMapText}
                onChange={e => setAgentIdMapText(e.target.value)}
                className="mt-1 w-full bg-gray-800 border border-gray-600 rounded px-2 py-1 text-xs font-mono text-gray-200"
              />
            </label>
          </div>

          <div className="flex items-center gap-3 text-xs text-gray-300">
            <label className="inline-flex items-center gap-2"><input type="checkbox" checked={replaceExisting} onChange={e => setReplaceExisting(e.target.checked)} />Replace existing agents</label>
            <label className="inline-flex items-center gap-2"><input type="checkbox" checked={importRouting} onChange={e => setImportRouting(e.target.checked)} />Import routing</label>
            <label className="inline-flex items-center gap-2"><input type="checkbox" checked={importAgentTools} onChange={e => setImportAgentTools(e.target.checked)} />Import agent tools</label>
            <button onClick={doValidate} disabled={loading || !packageText.trim()} className="ml-auto text-xs px-3 py-1.5 rounded bg-blue-700 hover:bg-blue-600 text-white disabled:opacity-50">Validate</button>
            <button onClick={doImport} disabled={loading || !packageText.trim()} className="text-xs px-3 py-1.5 rounded bg-emerald-700 hover:bg-emerald-600 text-white disabled:opacity-50">Import</button>
          </div>
        </section>

        <section className="border border-gray-700 rounded p-3 bg-gray-900/40 space-y-3">
          <h3 className="text-sm text-gray-200 font-medium">Package Content (JSON5)</h3>
          <div
            onDragOver={e => {
              e.preventDefault()
              setDragOver(true)
            }}
            onDragLeave={() => setDragOver(false)}
            onDrop={e => void handleDrop(e)}
            className={[
              'border rounded p-2 text-xs transition-colors',
              dragOver
                ? 'border-emerald-500 bg-emerald-900/10 text-emerald-300'
                : 'border-gray-700 bg-gray-950/40 text-gray-400',
            ].join(' ')}
          >
            Drag & drop a package file here or
            <button
              onClick={() => fileInputRef.current?.click()}
              className="ml-2 px-2 py-1 rounded border border-gray-600 bg-gray-800 text-gray-200 hover:bg-gray-700"
              type="button"
            >
              Load package file
            </button>
            .
            <input
              ref={fileInputRef}
              type="file"
              accept=".json5,.json,.txt"
              className="hidden"
              onChange={e => void handleFileChange(e)}
            />
          </div>
          <textarea
            rows={18}
            value={packageText}
            onChange={e => setPackageText(e.target.value)}
            placeholder="Paste or edit package JSON5 here..."
            className="w-full bg-gray-800 border border-gray-600 rounded px-2 py-2 text-xs font-mono text-gray-200"
          />
        </section>

        <section className="border border-gray-700 rounded p-3 bg-gray-900/40 space-y-2">
          <h3 className="text-sm text-gray-200 font-medium">Validation Report</h3>
          {!validation && <p className="text-xs text-gray-500">Run validation to see issues.</p>}
          {validation && (
            <>
              <p className={validation.ok ? 'text-xs text-emerald-400' : 'text-xs text-amber-300'}>
                {validation.ok ? 'No blocking issues found.' : 'Validation found issues.'}
              </p>
              <div className="max-h-56 overflow-y-auto border border-gray-700 rounded">
                <table className="w-full text-xs">
                  <thead className="bg-gray-900 text-gray-300">
                    <tr>
                      <th className="text-left px-2 py-1">Level</th>
                      <th className="text-left px-2 py-1">Path</th>
                      <th className="text-left px-2 py-1">Message</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(validation.problems ?? []).map((p, i) => (
                      <tr key={`${p.path}-${i}`} className="border-t border-gray-800">
                        <td className={`px-2 py-1 ${p.level === 'error' ? 'text-red-400' : 'text-amber-300'}`}>{p.level}</td>
                        <td className="px-2 py-1 text-gray-300 font-mono">{p.path}</td>
                        <td className="px-2 py-1 text-gray-300">{p.message}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </section>
      </div>
    </div>
  )
}

