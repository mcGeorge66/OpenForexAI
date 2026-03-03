/**
 * ConfigViewer — fetches a config endpoint and renders pretty-printed JSON
 * with basic syntax highlighting.
 */

import { useEffect, useState } from 'react'
import { RefreshCw } from 'lucide-react'

interface ConfigViewerProps {
  /** Fetch URL, e.g. '/config/view' or '/config/files/event_routing' */
  url: string
  title: string
}

/** Very small JSON syntax highlighter — no library, no dependencies */
function highlight(json: string): string {
  return json
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(
      /("(\\u[a-zA-Z0-9]{4}|\\[^u]|[^\\"])*"(\s*:)?|\b(true|false|null)\b|-?\d+(?:\.\d*)?(?:[eE][+\-]?\d+)?)/g,
      match => {
        if (/^"/.test(match)) {
          if (/:$/.test(match)) {
            // key
            return `<span style="color:#7dd3fc">${match}</span>`
          }
          // string value — check if it's "***" (masked)
          if (match === '"***"') {
            return `<span style="color:#f87171">${match}</span>`
          }
          return `<span style="color:#86efac">${match}</span>`
        }
        if (/true|false/.test(match)) {
          return `<span style="color:#fbbf24">${match}</span>`
        }
        if (/null/.test(match)) {
          return `<span style="color:#9ca3af">${match}</span>`
        }
        return `<span style="color:#c4b5fd">${match}</span>`
      },
    )
}

export function ConfigViewer({ url, title }: ConfigViewerProps) {
  const [data, setData] = useState<unknown>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = () => {
    setLoading(true)
    setError(null)
    fetch(url)
      .then(r => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`)
        return r.json()
      })
      .then(json => { setData(json); setLoading(false) })
      .catch(err => { setError(String(err)); setLoading(false) })
  }

  useEffect(() => { load() }, [url]) // eslint-disable-line react-hooks/exhaustive-deps

  const pretty = data !== null ? JSON.stringify(data, null, 2) : null

  return (
    <div className="flex flex-col h-full">
      {/* Toolbar */}
      <div className="flex items-center justify-between px-4 py-2 bg-gray-900 border-b border-gray-700 flex-shrink-0">
        <span className="text-sm text-gray-300 font-medium">{title}</span>
        <div className="flex items-center gap-3">
          <span className="text-xs text-gray-500">{url}</span>
          <button
            onClick={load}
            disabled={loading}
            className="flex items-center gap-1 text-xs text-gray-400 hover:text-gray-200 transition-colors"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-auto p-4 bg-gray-950">
        {loading && (
          <p className="text-gray-500 text-sm animate-pulse">Loading…</p>
        )}
        {error && (
          <p className="text-red-400 text-sm">Error: {error}</p>
        )}
        {pretty && !loading && (
          <pre
            className="text-xs font-mono leading-5 text-gray-300"
            dangerouslySetInnerHTML={{ __html: highlight(pretty) }}
          />
        )}
      </div>
    </div>
  )
}
