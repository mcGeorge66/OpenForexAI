import { useEffect, useRef, useState } from 'react'
import Editor from '@monaco-editor/react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import rehypeRaw from 'rehype-raw'
import { Columns, Edit3, Eye, Save } from 'lucide-react'
import { api } from '@/api/client'

type ViewMode = 'edit' | 'split' | 'preview'

const PROSE = [
  '[&_h1]:text-2xl [&_h1]:font-bold [&_h1]:text-white [&_h1]:mt-6 [&_h1]:mb-3 [&_h1]:border-b [&_h1]:border-gray-700 [&_h1]:pb-2',
  '[&_h2]:text-xl [&_h2]:font-semibold [&_h2]:text-white [&_h2]:mt-5 [&_h2]:mb-2',
  '[&_h3]:text-lg [&_h3]:font-semibold [&_h3]:text-gray-100 [&_h3]:mt-4 [&_h3]:mb-2',
  '[&_p]:my-3 [&_p]:text-gray-300 [&_p]:leading-7',
  '[&_ul]:list-disc [&_ul]:pl-6 [&_ul]:my-3',
  '[&_ol]:list-decimal [&_ol]:pl-6 [&_ol]:my-3',
  '[&_li]:my-1 [&_li]:text-gray-300',
  '[&_code]:font-mono [&_code]:text-emerald-300 [&_code]:bg-gray-900 [&_code]:px-1.5 [&_code]:py-0.5 [&_code]:rounded [&_code]:text-sm',
  '[&_pre]:bg-gray-900 [&_pre]:border [&_pre]:border-gray-700 [&_pre]:rounded [&_pre]:p-3 [&_pre]:overflow-auto [&_pre]:my-4',
  '[&_pre_code]:bg-transparent [&_pre_code]:p-0',
  '[&_table]:w-full [&_table]:border-collapse [&_table]:my-4 [&_table]:text-sm',
  '[&_thead_th]:text-left [&_thead_th]:text-gray-200 [&_thead_th]:font-semibold [&_thead_th]:border-b [&_thead_th]:border-gray-600 [&_thead_th]:px-3 [&_thead_th]:py-2',
  '[&_tbody_td]:border-b [&_tbody_td]:border-gray-800 [&_tbody_td]:px-3 [&_tbody_td]:py-2 [&_tbody_td]:text-gray-300',
  '[&_hr]:border-gray-700 [&_hr]:my-6',
].join(' ')

export function LlmContextEditor() {
  const [files, setFiles] = useState<string[]>([])
  const [selected, setSelected] = useState<string>('')
  const [content, setContent] = useState<string>('')
  const [originalContent, setOriginalContent] = useState<string>('')
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [viewMode, setViewMode] = useState<ViewMode>('split')
  const editorRef = useRef<{ getValue: () => string } | null>(null)

  useEffect(() => {
    void api.llmContextList().then(setFiles).catch(() => setFiles([]))
  }, [])

  const loadFile = async (filename: string) => {
    if (!filename) { setContent(''); setOriginalContent(''); return }
    setLoading(true)
    setError(null)
    try {
      const res = await api.llmContextGet(filename)
      setContent(res.content)
      setOriginalContent(res.content)
    } catch (e) {
      setError(`Failed to load: ${String(e)}`)
    } finally {
      setLoading(false)
    }
  }

  const handleSelect = (filename: string) => {
    setSelected(filename)
    void loadFile(filename)
  }

  const handleSave = async () => {
    if (!selected) return
    const current = editorRef.current?.getValue() ?? content
    setSaving(true)
    setError(null)
    try {
      await api.llmContextSave(selected, current)
      setOriginalContent(current)
      setContent(current)
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    } catch (e) {
      setError(`Failed to save: ${String(e)}`)
    } finally {
      setSaving(false)
    }
  }

  const dirty = content !== originalContent

  return (
    <div className="h-full flex flex-col bg-gray-950 text-gray-100 overflow-hidden">
      {/* Top bar */}
      <div className="flex items-center gap-3 px-4 py-2 bg-gray-900 border-b border-gray-700 flex-shrink-0">
        <span className="text-sm text-gray-400 font-medium">AI-Assistant Context</span>
        <select
          value={selected}
          onChange={e => handleSelect(e.target.value)}
          className="bg-gray-800 border border-gray-600 rounded px-2 py-1 text-sm text-gray-200 min-w-52"
        >
          <option value="">— none —</option>
          {files.map(f => <option key={f} value={f}>{f}</option>)}
        </select>

        {selected && (
          <>
            <div className="flex items-center gap-1 ml-2">
              {([
                { mode: 'edit' as ViewMode,    icon: <Edit3 className="w-3.5 h-3.5" />,    title: 'Edit'    },
                { mode: 'split' as ViewMode,   icon: <Columns className="w-3.5 h-3.5" />,  title: 'Split'   },
                { mode: 'preview' as ViewMode, icon: <Eye className="w-3.5 h-3.5" />,      title: 'Preview' },
              ] as const).map(({ mode, icon, title }) => (
                <button
                  key={mode}
                  onClick={() => setViewMode(mode)}
                  title={title}
                  className={`flex items-center gap-1 px-2 py-1 rounded border text-xs ${
                    viewMode === mode
                      ? 'border-emerald-500 bg-emerald-900/40 text-emerald-300'
                      : 'border-gray-700 bg-gray-800 text-gray-400 hover:text-white'
                  }`}
                >
                  {icon}
                </button>
              ))}
            </div>
            <button
              onClick={() => void handleSave()}
              disabled={saving || !dirty}
              className="flex items-center gap-1.5 px-3 py-1 rounded border border-gray-600 bg-gray-800 text-gray-300 hover:text-white disabled:opacity-40 text-sm ml-auto"
            >
              <Save className="w-3.5 h-3.5" />
              {saved ? '✓ Saved' : saving ? 'Saving…' : 'Save'}
            </button>
          </>
        )}

        {error && <span className="text-xs text-red-400 ml-2">{error}</span>}
      </div>

      {/* Editor area */}
      {!selected ? (
        <div className="flex-1 flex items-center justify-center text-gray-600 text-sm">
          Select a context file to edit
        </div>
      ) : loading ? (
        <div className="flex-1 flex items-center justify-center text-gray-600 text-sm animate-pulse">
          Loading…
        </div>
      ) : (
        <div className="flex-1 min-h-0 flex overflow-hidden">
          {(viewMode === 'edit' || viewMode === 'split') && (
            <div className={viewMode === 'split' ? 'w-1/2 border-r border-gray-700' : 'w-full'}>
              <Editor
                height="100%"
                defaultLanguage="markdown"
                theme="vs-dark"
                value={content}
                onChange={v => setContent(v ?? '')}
                onMount={editor => { editorRef.current = editor }}
                options={{ minimap: { enabled: false }, wordWrap: 'on', fontSize: 13, lineNumbers: 'on' }}
              />
            </div>
          )}
          {(viewMode === 'preview' || viewMode === 'split') && (
            <div className={`${viewMode === 'split' ? 'w-1/2' : 'w-full'} overflow-auto p-6`}>
              <article className={`max-w-none text-sm ${PROSE}`}>
                <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeRaw]}>
                  {content}
                </ReactMarkdown>
              </article>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
