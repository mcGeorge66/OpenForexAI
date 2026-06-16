/**
 * ModuleConfigViewer — select an LLM or broker module and edit/save its
 * raw JSON5 config text (comments preserved).
 */

import { useEffect, useState } from 'react'
import JSON5 from 'json5'
import { RefreshCw, Save } from 'lucide-react'
import { api } from '@/api/client'
import { useProjectRoot } from '@/api/useProjectRoot'
import { Json5MonacoEditor } from '@/components/common/Json5MonacoEditor'

interface ModuleConfigViewerProps {
  moduleType: 'llm' | 'broker'
}

export function ModuleConfigViewer({ moduleType }: ModuleConfigViewerProps) {
  const root = useProjectRoot()
  const [names, setNames] = useState<string[]>([])
  const [namesLoading, setNamesLoading] = useState(true)
  const [namesError, setNamesError] = useState<string | null>(null)

  const [selectedName, setSelectedName] = useState('')
  const [text, setText] = useState('')
  const [configLoading, setConfigLoading] = useState(false)
  const [configError, setConfigError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [saveMessage, setSaveMessage] = useState<string | null>(null)
  const [cursor, setCursor] = useState({ line: 1, column: 1 })
  const [pathLabel, setPathLabel] = useState('')

  const title = moduleType === 'llm' ? 'LLM Modules' : 'Broker Modules'

  useEffect(() => {
    setNames([])
    setNamesLoading(true)
    setNamesError(null)
    setSelectedName('')
    setText('')
    setConfigError(null)
    setSaveError(null)
    setSaveMessage(null)
    setCursor({ line: 1, column: 1 })
    setPathLabel('')

    api.getModuleNames(moduleType)
      .then(resp => {
        setNames(resp.names)
        setNamesLoading(false)
      })
      .catch(err => {
        setNamesError(String(err))
        setNamesLoading(false)
      })
  }, [moduleType])

  const loadConfig = () => {
    if (!selectedName) {
      return
    }
    setConfigLoading(true)
    setConfigError(null)
    setSaveError(null)
    setSaveMessage(null)

    Promise.all([
      api.getModuleConfigRawText(moduleType, selectedName),
      api.getSystemConfig(),
    ])
      .then(([raw, systemCfg]) => {
        setText(raw)
        const relPath = (systemCfg as Record<string, unknown>)?.modules &&
          typeof (systemCfg as Record<string, unknown>).modules === 'object'
          ? ((systemCfg as { modules?: Record<string, Record<string, unknown>> }).modules?.[moduleType]?.[selectedName] as unknown)
          : undefined
        const relStr = typeof relPath === 'string' && relPath.trim() ? relPath : ''
        const sep = root.includes('\\') ? '\\' : '/'
        setPathLabel(relStr ? (/^[A-Za-z]:[\\\/]/.test(relStr) ? relStr : (root ? root + sep + relStr.replaceAll('/', sep) : relStr)) : '')
        setCursor({ line: 1, column: 1 })
        setConfigLoading(false)
      })
      .catch(err => {
        setConfigError(String(err))
        setConfigLoading(false)
      })
  }

  useEffect(() => {
    if (!selectedName) {
      setText('')
      setPathLabel('')
      setConfigError(null)
      return
    }
    loadConfig()
  }, [moduleType, selectedName]) // eslint-disable-line react-hooks/exhaustive-deps

  const saveConfig = async () => {
    if (!selectedName) return
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
      await api.saveModuleConfigRaw(moduleType, selectedName, text)
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
          {selectedName && pathLabel && (
            <span className="text-xs text-gray-500">{pathLabel}</span>
          )}
          {selectedName && (
            <span className="text-xs text-gray-500">Position {cursor.line}:{cursor.column}</span>
          )}
          <button
            onClick={saveConfig}
            disabled={!selectedName || configLoading || saving}
            className="flex items-center gap-1 text-xs text-gray-400 hover:text-gray-200 transition-colors disabled:opacity-40"
          >
            <Save className="w-3.5 h-3.5" />
            {saving ? 'Saving…' : 'Save'}
          </button>
          <button
            onClick={loadConfig}
            disabled={!selectedName || configLoading}
            className="flex items-center gap-1 text-xs text-gray-400 hover:text-gray-200 transition-colors disabled:opacity-40"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${configLoading ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        </div>
      </div>

      <div className="px-4 py-3 bg-gray-900 border-b border-gray-700 flex-shrink-0">
        <label className="block text-xs text-gray-400 mb-1">
          Select {moduleType === 'llm' ? 'LLM module' : 'broker module'}
        </label>
        {namesError ? (
          <p className="text-red-400 text-xs">Error loading modules: {namesError}</p>
        ) : (
          <select
            value={selectedName}
            onChange={e => setSelectedName(e.target.value)}
            disabled={namesLoading}
            className="w-full max-w-sm bg-gray-800 text-gray-200 text-sm rounded px-2 py-1.5 border border-gray-600 focus:outline-none focus:border-emerald-500"
          >
            <option value="">
              {namesLoading ? 'Loading…' : `— select ${moduleType} module —`}
            </option>
            {names.map(n => (
              <option key={n} value={n}>{n}</option>
            ))}
          </select>
        )}
      </div>

      <div className="flex-1 min-h-0 flex flex-col bg-gray-950">
        {(!selectedName || configLoading || configError || saveError || saveMessage) && (
          <div className="px-4 py-2 flex-shrink-0">
            {!selectedName && (
              <p className="text-gray-500 text-sm italic">
                Select a {moduleType === 'llm' ? 'LLM' : 'broker'} module above to view its configuration.
              </p>
            )}
            {selectedName && configLoading && (
              <p className="text-gray-500 text-sm animate-pulse">Loading…</p>
            )}
            {selectedName && configError && (
              <p className="text-red-400 text-sm">Error: {configError}</p>
            )}
            {saveError && <p className="text-red-400 text-sm">Error: {saveError}</p>}
            {saveMessage && <p className="text-emerald-400 text-sm">{saveMessage}</p>}
          </div>
        )}
        {selectedName && !configLoading && (
          <div className="flex-1 min-h-0 border-t border-gray-800">
            <Json5MonacoEditor
              value={text}
              onChange={setText}
              onCursorChange={(line, column) => setCursor({ line, column })}
            />
          </div>
        )}
      </div>
    </div>
  )
}
