import { useEffect, useState } from 'react'
import { RefreshCw } from 'lucide-react'
import { api, type InitialConsoleResponse } from '@/api/client'

const EMPTY: InitialConsoleResponse = {
  logo: [],
  llm: { configured_count: 0, connected_count: 0, items: [] },
  broker: { configured_count: 0, connected_count: 0, items: [] },
  agents: { configured_count: 0, enabled_count: 0, items: [] },
  version: {
    local: 'unknown',
    remote: null,
    remote_prerelease: null,
    remote_published_at: null,
    remote_url: null,
    remote_error: null,
  },
  timestamp: '',
}

function badge(status: string): string {
  if (status === 'connected') return 'bg-emerald-900/40 text-emerald-300 border border-emerald-700/60'
  if (status === 'missing') return 'bg-red-900/30 text-red-300 border border-red-700/60'
  return 'bg-gray-800 text-gray-300 border border-gray-700'
}

export function InitialPage() {
  const [data, setData] = useState<InitialConsoleResponse>(EMPTY)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = () => {
    setLoading(true)
    setError(null)
    api.getInitialConsole()
      .then(resp => {
        setData(resp)
        setLoading(false)
      })
      .catch(err => {
        setError(String(err))
        setLoading(false)
      })
  }

  useEffect(() => {
    load()
  }, [])

  return (
    <div className="flex flex-col h-full bg-gray-950 text-gray-200">
      <div className="flex items-center justify-between px-4 py-2 bg-gray-900 border-b border-gray-700">
        <span className="text-sm text-gray-300 font-medium">Initial</span>
        <button
          onClick={load}
          disabled={loading}
          className="flex items-center gap-1 text-xs text-gray-400 hover:text-gray-200 transition-colors disabled:opacity-50"
          title="Refresh"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          Refresh
        </button>
      </div>

      <div className="flex-1 overflow-auto p-4 space-y-4">
        {error && <div className="text-sm text-red-400">Error: {error}</div>}

        <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
          <section className="bg-gray-900 border border-gray-700 rounded-lg p-4">
            <pre className="text-xs text-emerald-300 leading-4 overflow-auto">{(data.logo || []).join('\n')}</pre>
          </section>

          <section className="bg-gray-900 border border-gray-700 rounded-lg p-4">
            <h3 className="text-sm font-semibold text-gray-100 mb-2">Version</h3>
            <div className="text-xs text-gray-300 space-y-1">
              <div>Local: <span className="font-mono text-emerald-300">{data.version.local}</span></div>
              <div>
                Internet: <span className="font-mono text-cyan-300">{data.version.remote || '-'}</span>
                {data.version.remote_prerelease ? <span className="text-amber-300"> (pre-release)</span> : null}
              </div>
              {data.version.remote_published_at && <div>Published: {data.version.remote_published_at}</div>}
              {data.version.remote_url && (
                <div>
                  Release: <a className="text-cyan-300 hover:text-cyan-200 underline" href={data.version.remote_url} target="_blank" rel="noreferrer">{data.version.remote_url}</a>
                </div>
              )}
              {data.version.remote_error && <div className="text-amber-300">Remote check: {data.version.remote_error}</div>}
              {data.timestamp && <div className="text-gray-500">Snapshot: {data.timestamp}</div>}
            </div>
          </section>
        </div>

        <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
          <section className="bg-gray-900 border border-gray-700 rounded-lg p-4">
            <h3 className="text-sm font-semibold text-gray-100 mb-2">LLM Interfaces</h3>
            <p className="text-xs text-gray-400 mb-3">
              Configured: <span className="text-gray-200">{data.llm.configured_count}</span>
              {' · '}
              Connected: <span className="text-emerald-300">{data.llm.connected_count}</span>
            </p>
            <div className="space-y-2">
              {data.llm.items.map(item => (
                <div key={item.name} className="flex items-center justify-between gap-2 text-xs">
                  <span className="text-gray-200 font-mono">{item.name}</span>
                  <span className={`px-2 py-0.5 rounded ${badge(item.status)}`}>{item.status}</span>
                </div>
              ))}
              {data.llm.items.length === 0 && <p className="text-xs text-gray-500">No LLM modules configured.</p>}
            </div>
          </section>

          <section className="bg-gray-900 border border-gray-700 rounded-lg p-4">
            <h3 className="text-sm font-semibold text-gray-100 mb-2">Broker Interfaces</h3>
            <p className="text-xs text-gray-400 mb-3">
              Configured: <span className="text-gray-200">{data.broker.configured_count}</span>
              {' · '}
              Connected: <span className="text-emerald-300">{data.broker.connected_count}</span>
            </p>
            <div className="space-y-2">
              {data.broker.items.map(item => (
                <div key={item.name} className="flex items-center justify-between gap-2 text-xs">
                  <div className="flex flex-col">
                    <span className="text-gray-200 font-mono">{item.name}</span>
                    {item.short_name && <span className="text-[11px] text-gray-500">short_name: {item.short_name}</span>}
                  </div>
                  <span className={`px-2 py-0.5 rounded ${badge(item.status)}`}>{item.status}</span>
                </div>
              ))}
              {data.broker.items.length === 0 && <p className="text-xs text-gray-500">No broker modules configured.</p>}
            </div>
          </section>
        </div>

        <section className="bg-gray-900 border border-gray-700 rounded-lg p-4">
          <h3 className="text-sm font-semibold text-gray-100 mb-2">Configured Agents</h3>
          <p className="text-xs text-gray-400 mb-3">
            Total: <span className="text-gray-200">{data.agents.configured_count}</span>
            {' · '}
            Enabled: <span className="text-emerald-300">{data.agents.enabled_count}</span>
          </p>
          <div className="overflow-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-left text-gray-400 border-b border-gray-700">
                  <th className="py-2 pr-2">Agent</th>
                  <th className="py-2 pr-2">Status</th>
                  <th className="py-2 pr-2">Type</th>
                  <th className="py-2 pr-2">Broker</th>
                  <th className="py-2 pr-2">LLM</th>
                  <th className="py-2 pr-2">Pair</th>
                  <th className="py-2">Task</th>
                </tr>
              </thead>
              <tbody>
                {data.agents.items.map(agent => (
                  <tr key={agent.agent_id} className="border-b border-gray-800 align-top">
                    <td className="py-2 pr-2 font-mono text-gray-200">{agent.agent_id}</td>
                    <td className="py-2 pr-2">
                      <span className={`px-2 py-0.5 rounded ${agent.enabled ? badge('connected') : badge('missing')}`}>
                        {agent.enabled ? 'enabled' : 'disabled'}
                      </span>
                    </td>
                    <td className="py-2 pr-2 text-gray-300">{agent.type || '-'}</td>
                    <td className="py-2 pr-2 text-gray-300">{agent.broker || '-'}</td>
                    <td className="py-2 pr-2 text-gray-300">{agent.llm || '-'}</td>
                    <td className="py-2 pr-2 text-gray-300">{agent.pair || '-'}</td>
                    <td className="py-2 text-gray-300">{agent.task}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

      </div>
    </div>
  )
}
