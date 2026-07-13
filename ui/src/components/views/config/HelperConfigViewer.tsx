import { useCallback, useEffect, useRef, useState } from 'react'
import MonacoEditor, { type Monaco } from '@monaco-editor/react'
import type { editor as MonacoEditorNS } from 'monaco-editor'
import { BookOpen, Check, Copy, MessageSquare, RefreshCw, Save } from 'lucide-react'
import { api } from '@/api/client'
import { AiAssistantModal } from '@/components/common/AiAssistantModal'
import { SnippetLibraryModal } from '@/components/common/SnippetLibraryModal'
import { useProjectRoot, joinPath } from '@/api/useProjectRoot'

type SavedRange = { startLineNumber: number; startColumn: number; endLineNumber: number; endColumn: number }

export function HelperConfigViewer() {
  const root = useProjectRoot()
  const editorRef = useRef<MonacoEditorNS.IStandaloneCodeEditor | null>(null)
  const monacoRef = useRef<Monaco | null>(null)
  const savedSelectionRef = useRef<SavedRange | null>(null)

  const [text, setText] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [saveMessage, setSaveMessage] = useState<string | null>(null)
  const [cursorPos, setCursorPos] = useState({ line: 1, col: 1 })
  const [copied, setCopied] = useState(false)
  const [aiAssistantOpen, setAiAssistantOpen] = useState(false)
  const [libraryOpen, setLibraryOpen] = useState(false)

  // Live Python syntax validation
  useEffect(() => {
    const timer = setTimeout(async () => {
      const monaco = monacoRef.current
      const model = editorRef.current?.getModel()
      if (!monaco || !model) return
      try {
        const result = await api.validateScript({ code: text })
        monaco.editor.setModelMarkers(model, 'python-syntax', result.errors.map(e => ({
          severity: monaco.MarkerSeverity.Error,
          startLineNumber: e.line,
          startColumn: e.column,
          endLineNumber: e.line,
          endColumn: e.column + 1,
          message: `Syntax: ${e.message}`,
          source: 'Python',
        })))
      } catch {
        // non-fatal
      }
    }, 600)
    return () => clearTimeout(timer)
  }, [text])

  const load = useCallback(() => {
    setLoading(true)
    setError(null)
    setSaveError(null)
    setSaveMessage(null)
    api.getSnapshotHelpersText()
      .then(raw => {
        setText(raw)
        // Push value directly into Monaco model to avoid cursor reset
        const model = editorRef.current?.getModel()
        if (model && model.getValue() !== raw) model.setValue(raw)
        setLoading(false)
      })
      .catch(err => {
        setError(String(err))
        setLoading(false)
      })
  }, [])

  useEffect(() => { load() }, [load])

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

  const handleCopy = () => {
    void navigator.clipboard.writeText(text).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    })
  }

  const openLibrary = () => {
    const sel = editorRef.current?.getSelection()
    savedSelectionRef.current = sel
      ? { startLineNumber: sel.startLineNumber, startColumn: sel.startColumn, endLineNumber: sel.endLineNumber, endColumn: sel.endColumn }
      : null
    setLibraryOpen(true)
  }

  const insertAtCursor = (code: string) => {
    const editor = editorRef.current
    if (!editor) { setText(v => v ? `${v}\n${code}` : code); return }
    const isCollapsed = (r: SavedRange) =>
      r.startLineNumber === r.endLineNumber && r.startColumn === r.endColumn
    const position = editor.getPosition()
    const range = savedSelectionRef.current && !isCollapsed(savedSelectionRef.current)
      ? savedSelectionRef.current
      : savedSelectionRef.current ?? {
          startLineNumber: position!.lineNumber, startColumn: position!.column,
          endLineNumber: position!.lineNumber,   endColumn: position!.column,
        }
    editor.executeEdits('snippet-library', [{ range, text: code, forceMoveMarkers: true }])
    editor.focus()
    setText(editor.getValue())
    savedSelectionRef.current = null
  }

  const canSave = !loading && !saving

  return (
    <>
    <div className="flex flex-col h-full">

      {/* Toolbar */}
      <div className="flex items-center justify-between px-4 py-2 bg-gray-900 border-b border-gray-700 flex-shrink-0">
        <div className="flex items-center gap-3">
          <span className="text-sm text-gray-300 font-medium">Helper Config</span>
          <span className="text-xs text-gray-600">{root ? joinPath(root, 'config', 'snapshot_helpers.py') : 'config/snapshot_helpers.py'}</span>
        </div>
        <div className="flex items-center gap-3">
          {(saveMessage || saveError) && (
            <span className={`text-xs ${saveError ? 'text-red-400' : 'text-emerald-400'}`}>
              {saveError ?? saveMessage}
            </span>
          )}
          <span className="text-xs text-gray-600 font-mono select-none">Ln {cursorPos.line}, Col {cursorPos.col}</span>
          <button
            type="button" title="Snippet Library" onClick={openLibrary}
            className="flex items-center gap-1 text-xs text-gray-400 hover:text-gray-200 transition-colors"
          >
            <BookOpen className="w-3.5 h-3.5" />
          </button>
          <button
            type="button" title="Copy" onClick={handleCopy}
            className="flex items-center gap-1 text-xs text-gray-400 hover:text-gray-200 transition-colors"
          >
            {copied ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
          </button>
          <button
            onClick={() => setAiAssistantOpen(true)}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium bg-indigo-700 hover:bg-indigo-600 text-white border border-indigo-500/40 transition-colors"
            title="AI Assistant"
          >
            <MessageSquare className="w-3.5 h-3.5" />
            AI Assistant
          </button>
          <button
            onClick={() => void handleSave()} disabled={!canSave}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium bg-emerald-700 hover:bg-emerald-600 text-white disabled:opacity-40 transition-colors"
          >
            <Save className="w-3.5 h-3.5" />
            {saving ? 'Saving…' : 'Save'}
          </button>
          <button
            onClick={load} disabled={loading}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium bg-gray-700 hover:bg-gray-600 text-white disabled:opacity-40 transition-colors"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        </div>
      </div>

      {/* Shortkey hints */}
      <div className="flex items-center gap-4 px-4 py-1 bg-gray-950/60 border-b border-gray-700/50 text-[10px] text-gray-500 select-none overflow-x-auto flex-shrink-0">
        {([
          ['Ctrl+F', 'Find'],
          ['Ctrl+H', 'Replace'],
          ['Ctrl+/', 'Comment'],
          ['Ctrl+D', 'Select next'],
          ['Alt+↑↓', 'Move line'],
          ['Ctrl+Z', 'Undo'],
          ['Ctrl+Y', 'Redo'],
          ['Ctrl+S', 'Save'],
        ] as [string, string][]).map(([key, label]) => (
          <span key={key} className="flex items-center gap-1 whitespace-nowrap">
            <kbd className="font-mono bg-gray-800 border border-gray-700 rounded px-1 py-px text-gray-400 text-[9px]">{key}</kbd>
            <span>{label}</span>
          </span>
        ))}
      </div>

      {/* Editor */}
      <div className="flex-1 min-h-0">
        {loading && (
          <div className="flex items-center justify-center h-full text-gray-500 text-sm animate-pulse">Loading…</div>
        )}
        {error && (
          <div className="px-4 py-3 text-red-400 text-sm">Error: {error}</div>
        )}
        {!loading && !error && (
          <MonacoEditor
            height="100%"
            defaultLanguage="python"
            theme="vs-dark"
            value={text}
            onChange={v => setText(v ?? '')}
            onMount={(editor, monaco) => {
              editorRef.current = editor
              monacoRef.current = monaco
              editor.focus()
              editor.onDidChangeCursorPosition(e => {
                setCursorPos({ line: e.position.lineNumber, col: e.position.column })
              })
              // Ctrl+S → save
              editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyS, () => {
                void handleSave()
              })
            }}
            options={{
              minimap: { enabled: true },
              fontSize: 13,
              lineNumbers: 'on',
              scrollBeyondLastLine: false,
              wordWrap: 'on',
              tabSize: 4,
              insertSpaces: true,
              automaticLayout: true,
              scrollbar: { vertical: 'auto', horizontal: 'auto' },
              overviewRulerLanes: 0,
              renderLineHighlight: 'line',
              folding: true,
              foldingStrategy: 'indentation',
              showFoldingControls: 'always',
            }}
          />
        )}
      </div>

    </div>

    {aiAssistantOpen && (
      <AiAssistantModal
        title="AI Assistant — Snapshot Helpers"
        contextFile="entity_config_assistant.md"
        contextData={text}
        contextDataLabel="snapshot_helpers.py"
        onClose={() => setAiAssistantOpen(false)}
      />
    )}

    {libraryOpen && (
      <SnippetLibraryModal
        scope="script"
        onInsert={insertAtCursor}
        onClose={() => setLibraryOpen(false)}
      />
    )}
    </>
  )
}
