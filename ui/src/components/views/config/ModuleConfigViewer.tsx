/**
 * ModuleConfigViewer — select an LLM or broker module and edit/save its
 * raw JSON5 config text (comments preserved).
 */

import { useEffect, useRef, useState } from 'react'
import JSON5 from 'json5'
import { RefreshCw, Save } from 'lucide-react'
import { api } from '@/api/client'

interface ModuleConfigViewerProps {
  moduleType: 'llm' | 'broker'
}

const PROJECT_ROOT = 'D:\\GitHub\\GHG\\OpenForexAI'

function toDisplayPath(pathValue: unknown): string {
  if (typeof pathValue !== 'string' || !pathValue.trim()) return ''
  const normalized = pathValue.replaceAll('/', '\\')
  if (/^[A-Za-z]:\\/.test(normalized)) return normalized
  return `${PROJECT_ROOT}\\${normalized}`
}

export function ModuleConfigViewer({ moduleType }: ModuleConfigViewerProps) {
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
  const lineNumberRef = useRef<HTMLPreElement | null>(null)

  const title = moduleType === 'llm' ? 'LLM Modules' : 'Broker Modules'

  const syncCursor = (value: string, selectionStart: number) => {
    const before = value.slice(0, selectionStart)
    const lines = before.split('\n')
    const line = lines.length
    const column = lines[lines.length - 1].length + 1
    setCursor({ line, column })
  }

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
          ? ((systemCfg as Record<string, any>).modules?.[moduleType]?.[selectedName] as unknown)
          : undefined
        setPathLabel(toDisplayPath(relPath))
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

  const lineCount = Math.max(1, text.split('\n').length)
  const lineNumbers = Array.from({ length: lineCount }, (_, i) => String(i + 1)).join('\n')

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

      <div className="flex-1 overflow-auto p-4 bg-gray-950">
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
        {saveError && (
          <p className="text-red-400 text-sm mb-3">Error: {saveError}</p>
        )}
        {saveMessage && (
          <p className="text-emerald-400 text-sm mb-3">{saveMessage}</p>
        )}
        {selectedName && !configLoading && (
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
      </div>
    </div>
  )
}
