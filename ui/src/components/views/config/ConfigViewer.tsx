/**
 * ConfigViewer — read/edit/save JSON5 config documents.
 */

import { useEffect, useState } from 'react'
import JSON5 from 'json5'
import { RefreshCw, Save } from 'lucide-react'
import { Json5MonacoEditor } from '@/components/common/Json5MonacoEditor'

interface ConfigViewerProps {
  /** Display real file path in toolbar */
  pathLabel: string
  title: string
  loadConfig: () => Promise<string>
  saveConfig?: (content: Record<string, unknown> | string) => Promise<unknown>
}

export function ConfigViewer({ pathLabel, title, loadConfig, saveConfig }: ConfigViewerProps) {
  const [text, setText] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [saveMessage, setSaveMessage] = useState<string | null>(null)
  const [cursor, setCursor] = useState({ line: 1, column: 1 })

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

      <div className="flex-1 min-h-0 flex flex-col bg-gray-950">
        {(loading || error || saveError || saveMessage) && (
          <div className="px-4 py-2 flex-shrink-0">
            {loading && <p className="text-gray-500 text-sm animate-pulse">Loading…</p>}
            {error && <p className="text-red-400 text-sm">Error: {error}</p>}
            {saveError && <p className="text-red-400 text-sm">Error: {saveError}</p>}
            {saveMessage && <p className="text-emerald-400 text-sm">{saveMessage}</p>}
          </div>
        )}

        {!loading && (
          <div className="flex-1 min-h-0 border-t border-gray-800">
            <Json5MonacoEditor
              value={text}
              onChange={setText}
              onCursorChange={(line, column) => setCursor({ line, column })}
              readOnly={!saveConfig}
            />
          </div>
        )}
      </div>
    </div>
  )
}
