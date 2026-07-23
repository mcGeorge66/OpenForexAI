/**
 * PlainTextMonacoEditor — Monaco-backed editor for prose text (system prompts,
 * markdown notes) with line numbers, word wrap, and Monaco's built-in
 * find/replace widgets surfaced via a visible shortcut legend (same pattern
 * as ScriptEditor's fullscreen modal).
 */
import MonacoEditor, { type OnMount } from '@monaco-editor/react'

export interface PlainTextMonacoEditorProps {
  value: string
  onChange: (next: string) => void
  language?: 'plaintext' | 'markdown'
  readOnly?: boolean
  onMount?: OnMount
}

const SHORTCUT_HINTS: [string, string][] = [
  ['Ctrl+F', 'Find'],
  ['Ctrl+H', 'Replace'],
  ['Ctrl+Z', 'Undo'],
  ['Ctrl+Y', 'Redo'],
]

export function PlainTextMonacoEditor({
  value,
  onChange,
  language = 'plaintext',
  readOnly = false,
  onMount,
}: PlainTextMonacoEditorProps) {
  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center gap-4 px-3 py-1 bg-gray-950/60 border-b border-gray-700/50 text-[10px] text-gray-300 select-none overflow-x-auto flex-shrink-0">
        {SHORTCUT_HINTS.map(([key, label]) => (
          <span key={key} className="flex items-center gap-1 whitespace-nowrap">
            <kbd className="font-mono bg-gray-800 border border-gray-700 rounded px-1 py-px text-gray-300 text-[9px]">{key}</kbd>
            <span>{label}</span>
          </span>
        ))}
      </div>
      <div className="flex-1 min-h-0">
        <MonacoEditor
          height="100%"
          defaultLanguage={language}
          theme="vs-dark"
          value={value}
          onChange={v => onChange(v ?? '')}
          onMount={onMount}
          options={{
            readOnly,
            minimap: { enabled: false },
            fontSize: 13,
            fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Consolas, monospace',
            lineNumbers: 'on',
            wordWrap: 'on',
            scrollBeyondLastLine: false,
            automaticLayout: true,
            renderLineHighlight: 'line',
            scrollbar: { vertical: 'auto', horizontal: 'auto' },
            overviewRulerLanes: 0,
          }}
        />
      </div>
    </div>
  )
}
