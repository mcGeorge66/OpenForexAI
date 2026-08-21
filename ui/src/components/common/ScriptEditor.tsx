import type React from 'react'
import { useEffect, useRef, useState } from 'react'
import MonacoEditor, { type Monaco } from '@monaco-editor/react'
import type { editor as MonacoEditorNS } from 'monaco-editor'
import { Bot, BookOpen, Check, Copy, Maximize2, X } from 'lucide-react'
import { SnippetLibraryModal } from '@/components/common/SnippetLibraryModal'
import { ScriptAssistantPanel } from '@/components/common/ScriptAssistantPanel'
import { api } from '@/api/client'

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
  contextData?: string
  /** Render this instead of the built-in ScriptAssistantPanel in the "Assistant" tab —
   *  lets a caller share ONE assistant chat (same history/state) between this fullscreen
   *  view and another location (e.g. its own wizard's "LLM Assistant" tab) instead of
   *  each spinning up its own disconnected instance. Takes precedence over contextFile. */
  assistant?: React.ReactNode
}

function ExpandedEditorModal({ value: initialValue, onApply, onClose, snippetScope = 'script', contextFile, contextData, assistant }: ExpandedEditorModalProps) {
  const editorRef = useRef<MonacoEditorNS.IStandaloneCodeEditor | null>(null)
  const monacoRef = useRef<Monaco | null>(null)
  const savedSelectionRef = useRef<SavedRange | null>(null)
  const [libraryOpen, setLibraryOpen] = useState(false)
  const [cursorPos, setCursorPos] = useState({ line: 1, col: 1 })
  const [tab, setTab] = useState<'editor' | 'assistant'>('editor')

  // When a shared assistant is provided, this view has no draft of its own at all —
  // it reads/writes the exact same value the caller holds (like the inline editor
  // always has), so there's only ever one copy of the script to begin with. That's
  // the only way the assistant (which always writes to the caller's value, since it
  // may be invoked from either this view or elsewhere sharing the same chat) can never
  // write "into" a hidden draft this view would then clobber on Apply, or vice versa.
  //
  // Without a shared assistant, this is the ORIGINAL, unchanged behavior every other
  // ScriptEditor caller (SnapshotBlocksPanel, PromptWorkbench, ProfileConfigEditors, ...)
  // relies on: a draft captured once at mount, kept until Apply/Cancel, deliberately
  // NEVER resynced to the live value while open — this modal is unmounted/remounted
  // fresh on every open (`{modalOpen && <ExpandedEditorModal/>}`), so useState(initialValue)
  // already guarantees "start fresh each time"; no resync effect is needed OR safe here —
  // one would silently overwrite an unsaved draft if the caller's value changed for any
  // other reason while this modal happened to be open.
  const isLive = !!assistant
  const [draftValue, setDraftValue] = useState(initialValue)
  const currentValue = isLive ? initialValue : draftValue
  const setCurrentValue = (v: string) => { if (isLive) onApply(v); else setDraftValue(v) }

  useEffect(() => {
    const timer = setTimeout(async () => {
      const monaco = monacoRef.current
      const model = editorRef.current?.getModel()
      if (!monaco || !model) return
      try {
        const result = await api.validateScript({ code: currentValue })
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
        // non-fatal — editor stays usable if backend is unavailable
      }
    }, 600)
    return () => clearTimeout(timer)
  }, [currentValue])

  const openLibrary = () => {
    const sel = editorRef.current?.getSelection()
    savedSelectionRef.current = sel
      ? { startLineNumber: sel.startLineNumber, startColumn: sel.startColumn, endLineNumber: sel.endLineNumber, endColumn: sel.endColumn }
      : null
    setLibraryOpen(true)
  }

  const insertAtCursor = (code: string) => {
    const editor = editorRef.current
    if (!editor) { setCurrentValue(currentValue ? `${currentValue}\n${code}` : code); return }
    insertIntoEditor(editor, code, savedSelectionRef.current)
    savedSelectionRef.current = null
    // Sync state after Monaco edit
    setCurrentValue(editor.getValue())
  }

  const handleApply = () => { onApply(currentValue); onClose() }

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
            value={currentValue}
            onOpenLibrary={openLibrary}
            onClose={onClose}
          />

          {(assistant || contextFile) && (
            <div className="flex items-center gap-1 px-2 pt-1.5 bg-gray-900/60 border-b border-gray-700/50 flex-shrink-0">
              <button
                type="button"
                onClick={() => setTab('editor')}
                className={[
                  'px-3 py-1.5 text-xs transition-colors',
                  tab === 'editor'
                    ? 'text-emerald-300 border-b-2 border-emerald-400 -mb-px'
                    : 'text-white hover:text-gray-300',
                ].join(' ')}
              >
                Editor
              </button>
              <button
                type="button"
                onClick={() => setTab('assistant')}
                className={[
                  'px-3 py-1.5 text-xs transition-colors flex items-center gap-1',
                  tab === 'assistant'
                    ? 'text-emerald-300 border-b-2 border-emerald-400 -mb-px'
                    : 'text-white hover:text-gray-300',
                ].join(' ')}
              >
                <Bot className="w-3 h-3" />
                LLM Assistant
              </button>
            </div>
          )}

          {/* Both tabs stay mounted (only hidden via CSS) — Monaco keeps its editorRef
              valid for Apply/Cancel regardless of active tab, and the assistant's chat
              history survives switching back to Editor and forth. */}
          <div className={tab === 'editor' ? 'flex flex-col flex-1 min-h-0' : 'hidden'}>
            {/* Keyboard shortcut hints */}
            <div className="flex items-center gap-4 px-3 py-1 bg-gray-950/60 border-b border-gray-700/50 text-[10px] text-gray-300 select-none overflow-x-auto flex-shrink-0">
              {([
                ['Ctrl+F', 'Find'],
                ['Ctrl+H', 'Replace'],
                ['Ctrl+/', 'Comment'],
                ['Ctrl+D', 'Select next'],
                ['Alt+↑↓', 'Move line'],
                ['Ctrl+Z', 'Undo'],
                ['Ctrl+Y', 'Redo'],
              ] as [string, string][]).map(([key, label]) => (
                <span key={key} className="flex items-center gap-1 whitespace-nowrap">
                  <kbd className="font-mono bg-gray-800 border border-gray-700 rounded px-1 py-px text-gray-300 text-[9px]">{key}</kbd>
                  <span>{label}</span>
                </span>
              ))}
            </div>

            <div className="flex-1 min-h-0">
              <MonacoEditor
                height="100%"
                defaultLanguage="python"
                theme="vs-dark"
                value={currentValue}
                onChange={v => setCurrentValue(v ?? '')}
                onMount={(editor, monaco) => {
                  editorRef.current = editor
                  monacoRef.current = monaco
                  editor.focus()
                  editor.onDidChangeCursorPosition(e => {
                    setCursorPos({ line: e.position.lineNumber, col: e.position.column })
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
            </div>
          </div>

          {(assistant || contextFile) && (
            <div className={tab === 'assistant' ? 'flex flex-col flex-1 min-h-0' : 'hidden'}>
              {assistant ?? (
                <ScriptAssistantPanel
                  code={currentValue}
                  contextFile={contextFile as string}
                  contextData={contextData}
                  onApplyCode={v => setCurrentValue(v)}
                />
              )}
            </div>
          )}

          <div className="flex items-center justify-between gap-2 px-4 py-2 bg-gray-800/80 border-t border-gray-700">
            <span className="text-[10px] text-white font-mono select-none">
              Ln {cursorPos.line}, Col {cursorPos.col}
            </span>
            <div className="flex items-center gap-2">
              {isLive ? (
                // Live mode: every change (manual or via the assistant) already went
                // straight to the caller's value — nothing pending to accept or discard.
                <button
                  type="button"
                  onClick={onClose}
                  className="px-4 py-1.5 text-sm rounded bg-blue-600 hover:bg-blue-500 text-white font-medium transition-colors"
                >
                  Close
                </button>
              ) : (
                <>
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
                </>
              )}
            </div>
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
  /** Additional context for the LLM assistant (e.g. tool name + arguments) */
  contextData?: string
  /** Render this instead of the built-in ScriptAssistantPanel in the fullscreen "Assistant"
   *  tab — pass a chat driven by shared/lifted state to keep it in sync with another
   *  rendering of the same assistant elsewhere. Takes precedence over contextFile. */
  assistant?: React.ReactNode
}

export function ScriptEditor({
  value,
  onChange,
  minHeight = 160,
  placeholder,
  snippetScope = 'script',
  contextFile,
  contextData,
  assistant,
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
          contextData={contextData}
          assistant={assistant}
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
