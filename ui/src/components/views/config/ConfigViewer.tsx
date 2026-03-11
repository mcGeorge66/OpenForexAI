/**
 * ConfigViewer — read/edit/save JSON5 config documents.
 */

import { useEffect, useRef, useState } from 'react'
import JSON5 from 'json5'
import { RefreshCw, Save } from 'lucide-react'

interface ConfigViewerProps {
  /** Display real file path in toolbar */
  pathLabel: string
  title: string
  loadConfig: () => Promise<string>
  saveConfig?: (content: Record<string, unknown> | string) => Promise<unknown>
}

/** Very small JSON syntax highlighter — no library, no dependencies */
export function highlight(json: string): string {
  return json
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(
      /("(\\u[a-zA-Z0-9]{4}|\\[^u]|[^\\"])*"(\s*:)?|\b(true|false|null)\b|-?\d+(?:\.\d*)?(?:[eE][+\-]?\d+)?)/g,
      match => {
        if (/^"/.test(match)) {
          if (/:$/.test(match)) {
            return `<span style="color:#7dd3fc">${match}</span>`
          }
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

export function ConfigViewer({ pathLabel, title, loadConfig, saveConfig }: ConfigViewerProps) {
  const [text, setText] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [saveMessage, setSaveMessage] = useState<string | null>(null)
  const [cursor, setCursor] = useState({ line: 1, column: 1 })
  const lineNumberRef = useRef<HTMLPreElement | null>(null)

  const syncCursor = (value: string, selectionStart: number) => {
    const before = value.slice(0, selectionStart)
    const lines = before.split('\n')
    const line = lines.length
    const column = lines[lines.length - 1].length + 1
    setCursor({ line, column })
  }

  const load = () => {
    setLoading(true)
    setError(null)
    setSaveError(null)
    setSaveMessage(null)
    loadConfig()
      .then(raw => {
        setText(raw)
        setCursor({ line: 1, column: 1 })
        setLoading(false)
      })
      .catch(err => {
        setError(String(err))
        setLoading(false)
      })
  }

  useEffect(() => {
    load()
  }, [pathLabel]) // eslint-disable-line react-hooks/exhaustive-deps

  const canSave = !!saveConfig && !loading && !saving
  const lineCount = Math.max(1, text.split('\n').length)
  const lineNumbers = Array.from({ length: lineCount }, (_, i) => String(i + 1)).join('\n')

  const handleSave = async () => {
    if (!saveConfig) return
    setSaveError(null)
    setSaveMessage(null)

    let parsed: unknown
    try {
      parsed = JSON5.parse(text)
    } catch (err) {
      setSaveError(`Invalid JSON5: ${String(err)}`)
      return
    }
    if (!parsed || Array.isArray(parsed) || typeof parsed !== 'object') {
      setSaveError('Top-level JSON must be an object.')
      return
    }

    setSaving(true)
    try {
      await saveConfig(text)
      setSaveMessage('Saved.')
    } catch (err) {
      setSaveError(String(err))
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between px-4 py-2 bg-gray-900 border-b border-gray-700 flex-shrink-0">
        <span className="text-sm text-gray-300 font-medium">{title}</span>
        <div className="flex items-center gap-3">
          <span className="text-xs text-gray-500">{pathLabel}</span>
          {saveConfig && (
            <span className="text-xs text-gray-500">Position {cursor.line}:{cursor.column}</span>
          )}
          {saveConfig && (
            <button
              onClick={handleSave}
              disabled={!canSave}
              className="flex items-center gap-1 text-xs text-gray-400 hover:text-gray-200 transition-colors disabled:opacity-40"
            >
              <Save className="w-3.5 h-3.5" />
              {saving ? 'Saving…' : 'Save'}
            </button>
          )}
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

      <div className="flex-1 overflow-auto p-4 bg-gray-950">
        {loading && <p className="text-gray-500 text-sm animate-pulse">Loading…</p>}
        {error && <p className="text-red-400 text-sm">Error: {error}</p>}
        {saveError && <p className="text-red-400 text-sm mb-3">Error: {saveError}</p>}
        {saveMessage && <p className="text-emerald-400 text-sm mb-3">{saveMessage}</p>}

        {saveConfig && !loading && (
          <div className="w-full h-full min-h-[360px] bg-gray-900 text-gray-200 border border-gray-700 rounded overflow-hidden flex">
            <pre
              ref={lineNumberRef}
              className="w-14 flex-shrink-0 p-3 text-right text-xs font-mono leading-5 text-gray-500 bg-gray-950/70 border-r border-gray-800 overflow-hidden select-none"
            >
              {lineNumbers}
            </pre>
            <textarea
              value={text}
              onChange={e => {
                setText(e.target.value)
                syncCursor(e.target.value, e.target.selectionStart)
              }}
              onSelect={e => syncCursor(e.currentTarget.value, e.currentTarget.selectionStart)}
              onScroll={e => {
                if (lineNumberRef.current) {
                  lineNumberRef.current.scrollTop = e.currentTarget.scrollTop
                }
              }}
              spellCheck={false}
              className="flex-1 h-full p-3 bg-gray-900 text-gray-200 text-xs font-mono leading-5 focus:outline-none"
            />
          </div>
        )}

        {!saveConfig && !loading && (
          <pre
            className="text-xs font-mono leading-5 text-gray-300"
            dangerouslySetInnerHTML={{ __html: highlight(text) }}
          />
        )}
      </div>
    </div>
  )
}
