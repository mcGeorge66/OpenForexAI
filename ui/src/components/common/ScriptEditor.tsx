import { useCallback, useEffect, useRef, useState } from 'react'
import MonacoEditor from '@monaco-editor/react'
import type { editor as MonacoEditorNS } from 'monaco-editor'
import { BookOpen, Check, Copy, Maximize2, X } from 'lucide-react'
import { SnippetLibraryModal } from '@/components/common/SnippetLibraryModal'
import { LLMChatPanel } from '@/components/common/LLMChatPanel'

// ─── Toolbar ─────────────────────────────────────────────────────────────────

interface ToolbarProps {
  value: string
  onOpenLibrary: () => void
  onExpand?: () => void
  onClose?: () => void
}

function EditorToolbar({ value, onOpenLibrary, onExpand, onClose }: ToolbarProps) {
  const [copied, setCopied] = useState(false)

  const handleCopy = () => {
    void navigator.clipboard.writeText(value).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    })
  }

  return (
    <div className="flex items-center justify-end gap-1 px-2 py-1 bg-gray-800/60 border-b border-gray-700">
      {/* Snippet library button */}
      <button
        type="button"
        title="Snippet Library"
        onClick={onOpenLibrary}
        className="inline-flex items-center text-gray-500 hover:text-gray-300 transition-colors px-1"
      >
        <BookOpen className="w-3.5 h-3.5" />
      </button>

      {/* Copy button */}
      <button
        type="button"
        title="Copy to clipboard"
        onClick={handleCopy}
        className="inline-flex items-center text-gray-500 hover:text-gray-300 transition-colors px-1"
      >
        {copied ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
      </button>

      {/* Expand button (inline editor only) */}
      {onExpand && (
        <button
          type="button"
          title="Open in full-screen editor"
          onClick={onExpand}
          className="inline-flex items-center text-gray-500 hover:text-gray-300 transition-colors px-1"
        >
          <Maximize2 className="w-3.5 h-3.5" />
        </button>
      )}

      {/* Close button (modal only) */}
      {onClose && (
        <button
          type="button"
          title="Close"
          onClick={onClose}
          className="inline-flex items-center text-gray-500 hover:text-gray-300 transition-colors px-1 ml-1"
        >
          <X className="w-4 h-4" />
        </button>
      )}
    </div>
  )
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

type SavedRange = { startLineNumber: number; startColumn: number; endLineNumber: number; endColumn: number }

function insertIntoEditor(
  editor: MonacoEditorNS.IStandaloneCodeEditor,
  code: string,
  savedRange: SavedRange | null,
) {
  const isCollapsed = (r: SavedRange) =>
    r.startLineNumber === r.endLineNumber && r.startColumn === r.endColumn
  const position = editor.getPosition()
  const range = savedRange && !isCollapsed(savedRange)
    ? savedRange
    : savedRange ?? {
        startLineNumber: position!.lineNumber,
        startColumn: position!.column,
        endLineNumber: position!.lineNumber,
        endColumn: position!.column,
      }
  editor.executeEdits('snippet-library', [{ range, text: code, forceMoveMarkers: true }])
  editor.focus()
}

// ─── Full-screen modal ────────────────────────────────────────────────────────

interface ExpandedEditorModalProps {
  value: string
  onApply: (value: string) => void
  onClose: () => void
  snippetScope?: string
  contextFile?: string
}

const PANEL_MIN_HEIGHT = 80
const PANEL_MAX_HEIGHT = 600
const PANEL_DEFAULT_HEIGHT = 280

function ExpandedEditorModal({ value: initialValue, onApply, onClose, snippetScope = 'script', contextFile }: ExpandedEditorModalProps) {
  const editorRef = useRef<MonacoEditorNS.IStandaloneCodeEditor | null>(null)
  const savedSelectionRef = useRef<SavedRange | null>(null)
  const [localValue, setLocalValue] = useState(initialValue)
  const [libraryOpen, setLibraryOpen] = useState(false)
  const [panelHeight, setPanelHeight] = useState(PANEL_DEFAULT_HEIGHT)
  const dragStartY = useRef<number | null>(null)
  const dragStartHeight = useRef<number>(PANEL_DEFAULT_HEIGHT)

  const onDragHandleMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault()
    dragStartY.current = e.clientY
    dragStartHeight.current = panelHeight
  }, [panelHeight])

  useEffect(() => {
    const onMouseMove = (e: MouseEvent) => {
      if (dragStartY.current === null) return
      // dragging up = increasing panel height
      const delta = dragStartY.current - e.clientY
      const next = Math.min(PANEL_MAX_HEIGHT, Math.max(PANEL_MIN_HEIGHT, dragStartHeight.current + delta))
      setPanelHeight(next)
    }
    const onMouseUp = () => { dragStartY.current = null }
    window.addEventListener('mousemove', onMouseMove)
    window.addEventListener('mouseup', onMouseUp)
    return () => {
      window.removeEventListener('mousemove', onMouseMove)
      window.removeEventListener('mouseup', onMouseUp)
    }
  }, [])

  const openLibrary = () => {
    const sel = editorRef.current?.getSelection()
    savedSelectionRef.current = sel
      ? { startLineNumber: sel.startLineNumber, startColumn: sel.startColumn, endLineNumber: sel.endLineNumber, endColumn: sel.endColumn }
      : null
    setLibraryOpen(true)
  }

  const insertAtCursor = (code: string) => {
    const editor = editorRef.current
    if (!editor) { setLocalValue(v => v ? `${v}\n${code}` : code); return }
    insertIntoEditor(editor, code, savedSelectionRef.current)
    savedSelectionRef.current = null
    // Sync localValue after Monaco edit
    setLocalValue(editor.getValue())
  }

  const handleApply = () => { onApply(localValue); onClose() }

  const handleBackdropClick = (e: React.MouseEvent<HTMLDivElement>) => {
    if (e.target === e.currentTarget) onClose()
  }

  return (
    <>
      <div
        className="fixed inset-0 z-[200] flex items-center justify-center bg-black/70 backdrop-blur-sm p-6"
        onClick={handleBackdropClick}
      >
        <div
          className="flex flex-col w-full max-w-5xl rounded-lg border border-gray-600 bg-gray-900 shadow-2xl overflow-hidden"
          style={{ height: 'calc(100vh - 80px)' }}
          onClick={e => e.stopPropagation()}
        >
          <EditorToolbar
            value={localValue}
            onOpenLibrary={openLibrary}
            onClose={onClose}
          />

          <div className="flex-1 min-h-0">
            <MonacoEditor
              height="100%"
              defaultLanguage="python"
              theme="vs-dark"
              value={localValue}
              onChange={v => setLocalValue(v ?? '')}
              onMount={editor => {
                editorRef.current = editor
                editor.focus()
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
              }}
            />
          </div>

          {contextFile && (
            <>
              {/* Drag handle */}
              <div
                onMouseDown={onDragHandleMouseDown}
                className="flex-shrink-0 h-1.5 bg-gray-700 hover:bg-blue-600 cursor-row-resize transition-colors select-none"
                title="Drag to resize assistant panel"
              />
              <LLMChatPanel code={localValue} contextFile={contextFile} height={panelHeight} />
            </>
          )}

          <div className="flex items-center justify-end gap-2 px-4 py-3 bg-gray-800/80 border-t border-gray-700">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-1.5 text-sm rounded text-gray-400 hover:text-gray-200 hover:bg-gray-700 transition-colors"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={handleApply}
              className="px-4 py-1.5 text-sm rounded bg-blue-600 hover:bg-blue-500 text-white font-medium transition-colors"
            >
              Apply
            </button>
          </div>
        </div>
      </div>

      {libraryOpen && (
        <SnippetLibraryModal
          scope={snippetScope}
          onInsert={insertAtCursor}
          onClose={() => setLibraryOpen(false)}
        />
      )}
    </>
  )
}

// ─── Component ───────────────────────────────────────────────────────────────

interface ScriptEditorProps {
  value: string
  onChange: (value: string) => void
  minHeight?: number
  placeholder?: string
  snippetScope?: string
  /** If set, fullscreen modal shows the LLM assistant panel for this context file */
  contextFile?: string
}

export function ScriptEditor({
  value,
  onChange,
  minHeight = 160,
  placeholder,
  snippetScope = 'script',
  contextFile,
}: ScriptEditorProps) {
  const editorRef = useRef<MonacoEditorNS.IStandaloneCodeEditor | null>(null)
  const savedSelectionRef = useRef<SavedRange | null>(null)
  const [modalOpen, setModalOpen] = useState(false)
  const [libraryOpen, setLibraryOpen] = useState(false)

  const openLibrary = () => {
    const sel = editorRef.current?.getSelection()
    savedSelectionRef.current = sel
      ? { startLineNumber: sel.startLineNumber, startColumn: sel.startColumn, endLineNumber: sel.endLineNumber, endColumn: sel.endColumn }
      : null
    setLibraryOpen(true)
  }

  const insertAtCursor = (code: string) => {
    const editor = editorRef.current
    if (!editor) { onChange(value ? `${value}\n${code}` : code); return }
    insertIntoEditor(editor, code, savedSelectionRef.current)
    savedSelectionRef.current = null
  }

  return (
    <>
      <div className="relative rounded border border-gray-600 overflow-hidden bg-gray-900">
        <EditorToolbar
          value={value}
          onOpenLibrary={openLibrary}
          onExpand={() => setModalOpen(true)}
        />

        <MonacoEditor
          height={minHeight}
          defaultLanguage="python"
          theme="vs-dark"
          value={value}
          onChange={v => onChange(v ?? '')}
          onMount={editor => { editorRef.current = editor }}
          options={{
            minimap: { enabled: false },
            fontSize: 12,
            lineNumbers: 'on',
            scrollBeyondLastLine: false,
            wordWrap: 'on',
            tabSize: 4,
            insertSpaces: true,
            automaticLayout: true,
            scrollbar: { vertical: 'auto', horizontal: 'hidden' },
            overviewRulerLanes: 0,
            renderLineHighlight: 'line',
            placeholder: placeholder,
          }}
        />
      </div>

      {modalOpen && (
        <ExpandedEditorModal
          value={value}
          onApply={onChange}
          onClose={() => setModalOpen(false)}
          snippetScope={snippetScope}
          contextFile={contextFile}
        />
      )}

      {libraryOpen && (
        <SnippetLibraryModal
          scope={snippetScope}
          onInsert={insertAtCursor}
          onClose={() => setLibraryOpen(false)}
        />
      )}
    </>
  )
}
