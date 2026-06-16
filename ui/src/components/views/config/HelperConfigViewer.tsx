import { useEffect, useMemo, useRef, useState } from 'react'
import { RefreshCw, Save } from 'lucide-react'
import { api } from '@/api/client'
import { useProjectRoot, joinPath } from '@/api/useProjectRoot'

const LINE_HEIGHT_PX = 20
const EDITOR_PADDING_TOP_PX = 12

function parseFunctions(code: string): Array<{ name: string; line: number }> {
  return code
    .split('\n')
    .map((l, i) => ({ match: l.match(/^def\s+(\w+)\s*\(/), line: i + 1 }))
    .filter(({ match }) => match !== null)
    .map(({ match, line }) => ({ name: match![1], line }))
    .sort((a, b) => a.name.localeCompare(b.name))
}

export function HelperConfigViewer() {
  const root = useProjectRoot()
  const [text, setText] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [saveMessage, setSaveMessage] = useState<string | null>(null)
  const [cursor, setCursor] = useState({ line: 1, column: 1 })
  const [jumpTarget, setJumpTarget] = useState('')
  const lineNumberRef = useRef<HTMLPreElement | null>(null)
  const textareaRef = useRef<HTMLTextAreaElement | null>(null)

  const functions = useMemo(() => parseFunctions(text), [text])

  const syncCursor = (value: string, selectionStart: number) => {
    const before = value.slice(0, selectionStart)
    const lines = before.split('\n')
    const line = lines.length
    const column = lines[lines.length - 1].length + 1
    setCursor({ line, column })
  }

  const jumpToLine = (lineNumber: number) => {
    const ta = textareaRef.current
    if (!ta) return
    const lines = text.split('\n')
    let charPos = 0
    for (let i = 0; i < lineNumber - 1 && i < lines.length; i++) {
      charPos += lines[i].length + 1
    }
    ta.focus()
    ta.setSelectionRange(charPos, charPos)
    const scrollTop = Math.max(0, (lineNumber - 1) * LINE_HEIGHT_PX - EDITOR_PADDING_TOP_PX)
    ta.scrollTop = scrollTop
    if (lineNumberRef.current) lineNumberRef.current.scrollTop = scrollTop
    syncCursor(text, charPos)
  }

  const handleFunctionJump = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const lineStr = e.target.value
    setJumpTarget('')
    if (!lineStr) return
    jumpToLine(parseInt(lineStr, 10))
  }

  const load = () => {
    setLoading(true)
    setError(null)
    setSaveError(null)
    setSaveMessage(null)
    api.getSnapshotHelpersText()
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
  }, [])

  const handleSave = async () => {
    setSaveError(null)
    setSaveMessage(null)
    setSaving(true)
    try {
      await api.saveSnapshotHelpersText(text)
      setSaveMessage('Saved. Python syntax valid.')
    } catch (err) {
      setSaveError(String(err))
    } finally {
      setSaving(false)
    }
  }

  const canSave = !loading && !saving
  const lineCount = Math.max(1, text.split('\n').length)
  const lineNumbers = Array.from({ length: lineCount }, (_, i) => String(i + 1)).join('\n')

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between px-4 py-2 bg-gray-900 border-b border-gray-700 flex-shrink-0">
        <div className="flex items-center gap-3">
          <span className="text-sm text-gray-300 font-medium">Helper Config</span>
          {functions.length > 0 && (
            <select
              value={jumpTarget}
              onChange={handleFunctionJump}
              className="text-xs bg-gray-800 text-gray-300 border border-gray-700 rounded px-2 py-0.5 focus:outline-none focus:border-gray-500 cursor-pointer"
            >
              <option value="">Jump to function…</option>
              {functions.map(fn => (
                <option key={fn.line} value={String(fn.line)}>
                  {fn.name} (line {fn.line})
                </option>
              ))}
            </select>
          )}
        </div>
        <div className="flex items-center gap-3">
          <span className="text-xs text-gray-500">{root ? joinPath(root, 'config', 'snapshot_helpers.py') : 'config/snapshot_helpers.py'}</span>
          <span className="text-xs text-gray-500">Position {cursor.line}:{cursor.column}</span>
          <button
            onClick={handleSave}
            disabled={!canSave}
            className="flex items-center gap-1 text-xs text-gray-400 hover:text-gray-200 transition-colors disabled:opacity-40"
          >
            <Save className="w-3.5 h-3.5" />
            {saving ? 'Saving…' : 'Save'}
          </button>
          <button
            onClick={load}
            disabled={loading}
            className="flex items-center gap-1 text-xs text-gray-400 hover:text-gray-200 transition-colors disabled:opacity-40"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        </div>
      </div>

      <div className="px-4 py-3 bg-gray-900 border-b border-gray-700 flex-shrink-0">
        <p className="text-xs text-gray-400">
          Edit optional Python helper functions for snapshot transform scripts. Saving performs a final backend syntax check before the file is written.
        </p>
      </div>

      <div className="flex-1 overflow-auto p-4 bg-gray-950">
        {loading && <p className="text-gray-500 text-sm animate-pulse">Loading…</p>}
        {error && <p className="text-red-400 text-sm">Error: {error}</p>}
        {saveError && <p className="text-red-400 text-sm mb-3">Error: {saveError}</p>}
        {saveMessage && <p className="text-emerald-400 text-sm mb-3">{saveMessage}</p>}

        {!loading && (
          <div className="w-full h-full min-h-[360px] bg-gray-900 text-gray-200 border border-gray-700 rounded overflow-hidden flex">
            <pre
              ref={lineNumberRef}
              className="w-14 flex-shrink-0 p-3 text-right text-xs font-mono leading-5 text-gray-500 bg-gray-950/70 border-r border-gray-800 overflow-hidden select-none"
            >
              {lineNumbers}
            </pre>
            <textarea
              ref={textareaRef}
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
              placeholder="# Optional snapshot helper functions live here"
            />
          </div>
        )}
      </div>
    </div>
  )
}
