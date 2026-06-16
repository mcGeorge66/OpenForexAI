/**
 * Json5MonacoEditor — Monaco-backed editor for JSON5 documents.
 *
 * Configured for the editor views in /Config:
 * - jsonc language (tolerates // and /* * / comments)
 * - JSON validation OFF (otherwise trailing commas in JSON5 raise red squiggles)
 * - Folding enabled (collapse object/array branches)
 * - vs-dark theme, monospace font
 * - Reports cursor position back to the parent for the "Position L:C" status line
 */

import { useRef } from 'react'
import MonacoEditor, { type OnMount } from '@monaco-editor/react'
import type { editor as MonacoEditorNS } from 'monaco-editor'

export interface Json5MonacoEditorProps {
  value: string
  onChange: (next: string) => void
  onCursorChange?: (line: number, column: number) => void
  readOnly?: boolean
}

export function Json5MonacoEditor({
  value,
  onChange,
  onCursorChange,
  readOnly = false,
}: Json5MonacoEditorProps) {
  const editorRef = useRef<MonacoEditorNS.IStandaloneCodeEditor | null>(null)

  const handleMount: OnMount = (editor, monaco) => {
    editorRef.current = editor

    // Disable JSON validation diagnostics — we use jsonc as language for comment
    // support, but JSON5 trailing commas would still be flagged. Validation off
    // gives a clean editor; format errors surface on save via JSON5.parse().
    monaco.languages.json.jsonDefaults.setDiagnosticsOptions({
      validate: false,
      allowComments: true,
      schemas: [],
      enableSchemaRequest: false,
    })

    if (onCursorChange) {
      editor.onDidChangeCursorPosition(e => {
        onCursorChange(e.position.lineNumber, e.position.column)
      })
    }
  }

  return (
    <MonacoEditor
      height="100%"
      defaultLanguage="jsonc"
      theme="vs-dark"
      value={value}
      onChange={v => onChange(v ?? '')}
      onMount={handleMount}
      options={{
        readOnly,
        minimap: { enabled: false },
        fontSize: 12,
        fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Consolas, monospace',
        lineNumbers: 'on',
        folding: true,
        foldingStrategy: 'indentation',
        showFoldingControls: 'always',
        scrollBeyondLastLine: false,
        wordWrap: 'off',
        tabSize: 2,
        insertSpaces: true,
        automaticLayout: true,
        bracketPairColorization: { enabled: true },
        renderLineHighlight: 'line',
        scrollbar: { vertical: 'auto', horizontal: 'auto' },
        overviewRulerLanes: 0,
      }}
    />
  )
}
