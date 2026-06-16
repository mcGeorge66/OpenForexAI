import { useCallback, useEffect, useRef, useState } from 'react'
import Editor from '@monaco-editor/react'
import type * as Monaco from 'monaco-editor'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import rehypeRaw from 'rehype-raw'
import { headingSlug } from './TableOfContents'
import type { KbDocMeta } from '@/api/client'
import {
  Bold, Italic, Code, Link2, Table, List, ListOrdered,
  Quote, Minus, Eye, Edit3, Columns,
  Heading1, Heading2, Heading3, Image, Save,
} from 'lucide-react'

interface Props {
  docId: string
  title: string
  initialContent: string
  onTitleChange: (v: string) => void
  onSave: () => void
  saving?: boolean
  saved?: boolean
  docs: KbDocMeta[]
  onNavigate: (id: string) => void
  editorRefCallback?: (ref: { getValue: () => string } | null) => void
}

type ViewMode = 'edit' | 'split' | 'preview'

const PROSE = [
  '[&_h1]:text-2xl [&_h1]:font-bold [&_h1]:text-white [&_h1]:mt-6 [&_h1]:mb-3 [&_h1]:border-b [&_h1]:border-gray-700 [&_h1]:pb-2',
  '[&_h2]:text-xl [&_h2]:font-semibold [&_h2]:text-white [&_h2]:mt-5 [&_h2]:mb-2',
  '[&_h3]:text-lg [&_h3]:font-semibold [&_h3]:text-gray-100 [&_h3]:mt-4 [&_h3]:mb-2',
  '[&_p]:my-3 [&_p]:text-gray-300 [&_p]:leading-7',
  '[&_ul]:list-disc [&_ul]:pl-6 [&_ul]:my-3',
  '[&_ol]:list-decimal [&_ol]:pl-6 [&_ol]:my-3',
  '[&_li]:my-1 [&_li]:text-gray-300',
  '[&_a]:text-cyan-300 [&_a]:underline [&_a]:underline-offset-2 [&_a]:cursor-pointer hover:[&_a]:text-cyan-200',
  '[&_blockquote]:border-l-4 [&_blockquote]:border-emerald-600 [&_blockquote]:pl-4 [&_blockquote]:italic [&_blockquote]:text-gray-400 [&_blockquote]:my-4',
  '[&_code]:font-mono [&_code]:text-emerald-300 [&_code]:bg-gray-900 [&_code]:px-1.5 [&_code]:py-0.5 [&_code]:rounded [&_code]:text-sm',
  '[&_pre]:bg-gray-900 [&_pre]:border [&_pre]:border-gray-700 [&_pre]:rounded [&_pre]:p-3 [&_pre]:overflow-auto [&_pre]:my-4',
  '[&_pre_code]:bg-transparent [&_pre_code]:p-0',
  '[&_table]:w-full [&_table]:border-collapse [&_table]:my-4 [&_table]:text-sm',
  '[&_thead_th]:text-left [&_thead_th]:text-gray-200 [&_thead_th]:font-semibold [&_thead_th]:border-b [&_thead_th]:border-gray-600 [&_thead_th]:px-3 [&_thead_th]:py-2',
  '[&_tbody_td]:border-b [&_tbody_td]:border-gray-800 [&_tbody_td]:px-3 [&_tbody_td]:py-2 [&_tbody_td]:text-gray-300',
  '[&_tbody_tr:last-child_td]:border-0',
  '[&_hr]:border-gray-700 [&_hr]:my-6',
  '[&_img]:max-w-full [&_img]:rounded [&_img]:border [&_img]:border-gray-700',
  '[&_input[type=checkbox]]:mr-2',
  'marker:[&_li]:text-gray-500',
].join(' ')

function insert(editor: Monaco.editor.IStandaloneCodeEditor, text: string) {
  const selection = editor.getSelection()
  if (!selection) return
  editor.executeEdits('toolbar', [{ range: selection, text, forceMoveMarkers: true }])
  editor.focus()
}

function wrap(editor: Monaco.editor.IStandaloneCodeEditor, before: string, after: string) {
  const selection = editor.getSelection()
  if (!selection) return
  const model = editor.getModel()
  if (!model) return
  const selected = model.getValueInRange(selection)
  insert(editor, `${before}${selected || 'Text'}${after}`)
}

export function KbEditor({ docId, title, initialContent, onTitleChange, onSave, saving, saved, docs, onNavigate, editorRefCallback }: Props) {
  const editorRef = useRef<Monaco.editor.IStandaloneCodeEditor | null>(null)
  const [viewMode, setViewMode] = useState<ViewMode>('preview')
  // Preview content is managed locally — never causes parent re-renders
  const [previewContent, setPreviewContent] = useState(initialContent)

  // When docId changes (new document selected), reset Monaco and preview
  useEffect(() => {
    setPreviewContent(initialContent)
    if (editorRef.current) {
      editorRef.current.setValue(initialContent)
    }
  }, [docId]) // eslint-disable-line react-hooks/exhaustive-deps

  // Add "Bild einfügen" to Monaco's right-click context menu
  const setupImagePaste = useCallback((editor: Monaco.editor.IStandaloneCodeEditor) => {
    editor.addAction({
      id: 'insert-image-from-clipboard',
      label: 'Bild aus Zwischenablage einfügen',
      contextMenuGroupId: '1_modification',
      contextMenuOrder: 1,
      run: async (ed) => {
        try {
          const clipItems = await navigator.clipboard.read()
          for (const clipItem of clipItems) {
            const imageType = clipItem.types.find(t => t.startsWith('image/'))
            if (!imageType) continue
            const blob = await clipItem.getType(imageType)
            const reader = new FileReader()
            reader.onload = () => {
              const dataUrl = reader.result as string
              const md = `\n![image](${dataUrl})\n`
              const sel = ed.getSelection()
              if (sel) {
                ed.executeEdits('insert-image', [{ range: sel, text: md, forceMoveMarkers: true }])
                ed.focus()
              }
              setPreviewContent(ed.getValue())
            }
            reader.readAsDataURL(blob)
            return
          }
          alert('Kein Bild in der Zwischenablage gefunden.')
        } catch {
          alert('Zugriff auf Zwischenablage verweigert. Bitte Berechtigung im Browser erlauben.')
        }
      },
    })
  }, [])

  const buildInternalLinkMap = () => {
    const map = new Map<string, string>()
    for (const doc of docs) {
      map.set(doc.title.toLowerCase(), doc.id)
    }
    return map
  }

  const handleLinkClick = (href: string | undefined) => {
    if (!href) return
    if (href.startsWith('kb://')) {
      const id = href.slice(5)
      onNavigate(id)
      return
    }
    window.open(href, '_blank', 'noopener,noreferrer')
  }

  // Transform [[Title]] links in markdown to kb:// links for preview
  const processedContent = (() => {
    const linkMap = buildInternalLinkMap()
    return previewContent.replace(/\[\[([^\]]+)\]\]/g, (_, t) => {
      const id = linkMap.get(t.toLowerCase())
      return id ? `[${t}](kb://${id})` : `**[[${t}]]**`
    })
  })()

  const ModeBtn = ({ mode, label, icon: Icon }: { mode: ViewMode; label: string; icon: React.ElementType }) => (
    <button
      onClick={() => setViewMode(mode)}
      className={[
        'flex items-center gap-1 text-xs px-2 py-1 rounded transition-colors',
        viewMode === mode ? 'bg-emerald-900/40 text-emerald-300' : 'text-gray-400 hover:text-gray-200 hover:bg-gray-800',
      ].join(' ')}
      title={label}
    >
      <Icon className="w-3.5 h-3.5" />
    </button>
  )

  const ToolBtn = ({ title: t, icon: Icon, onClick }: { title: string; icon: React.ElementType; onClick: () => void }) => (
    <button
      onClick={onClick}
      className="flex items-center justify-center w-7 h-7 rounded text-gray-400 hover:text-gray-200 hover:bg-gray-700 transition-colors"
      title={t}
    >
      <Icon className="w-3.5 h-3.5" />
    </button>
  )

  const ed = () => editorRef.current!

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Title */}
      <div className="px-4 pt-3 pb-1 flex-shrink-0 border-b border-gray-800 print:px-0 print:pt-0">
        <input
          value={title}
          onChange={e => onTitleChange(e.target.value)}
          className="w-full bg-transparent text-xl font-bold text-white outline-none placeholder-gray-600 print:text-3xl"
          placeholder="Titel…"
        />
      </div>

      {/* Toolbar */}
      {(viewMode === 'edit' || viewMode === 'split') && (
        <div className="flex items-center gap-1 px-2 py-1 bg-gray-900 border-b border-gray-700 flex-shrink-0 flex-wrap print:hidden">
          <ToolBtn title="H1" icon={Heading1} onClick={() => insert(ed(), '\n# Überschrift\n')} />
          <ToolBtn title="H2" icon={Heading2} onClick={() => insert(ed(), '\n## Überschrift\n')} />
          <ToolBtn title="H3" icon={Heading3} onClick={() => insert(ed(), '\n### Überschrift\n')} />
          <div className="w-px h-5 bg-gray-700 mx-1" />
          <ToolBtn title="Fett" icon={Bold} onClick={() => wrap(ed(), '**', '**')} />
          <ToolBtn title="Kursiv" icon={Italic} onClick={() => wrap(ed(), '_', '_')} />
          <ToolBtn title="Code" icon={Code} onClick={() => wrap(ed(), '`', '`')} />
          <div className="w-px h-5 bg-gray-700 mx-1" />
          <ToolBtn title="Ungeordnete Liste" icon={List} onClick={() => insert(ed(), '\n- Element\n')} />
          <ToolBtn title="Geordnete Liste" icon={ListOrdered} onClick={() => insert(ed(), '\n1. Element\n')} />
          <ToolBtn title="Zitat" icon={Quote} onClick={() => insert(ed(), '\n> Zitat\n')} />
          <ToolBtn title="Trennlinie" icon={Minus} onClick={() => insert(ed(), '\n---\n')} />
          <div className="w-px h-5 bg-gray-700 mx-1" />
          <ToolBtn title="Link" icon={Link2} onClick={() => wrap(ed(), '[', '](https://)')} />
          <ToolBtn title="Interner Link [[Titel]]" icon={Link2}
            onClick={() => insert(ed(), '[[Dokumenttitel]]')} />
          <ToolBtn title="Bild einfügen" icon={Image}
            onClick={() => insert(ed(), '![Beschreibung](https://)')} />
          <div className="w-px h-5 bg-gray-700 mx-1" />
          <ToolBtn title="Tabelle einfügen" icon={Table}
            onClick={() => insert(ed(), '\n| Spalte 1 | Spalte 2 | Spalte 3 |\n|---|---|---|\n| Wert | Wert | Wert |\n')} />
          <div className="flex-1" />
          <button
            onClick={onSave}
            disabled={saving}
            className={[
              'flex items-center gap-1 text-xs px-2 py-1 rounded transition-colors mr-2',
              saved
                ? 'bg-emerald-600 text-white'
                : 'text-gray-400 hover:text-gray-200 hover:bg-gray-700 border border-gray-600',
              saving ? 'opacity-50 cursor-not-allowed' : '',
            ].join(' ')}
            title="Speichern (Ctrl+S)"
          >
            <Save className="w-3.5 h-3.5" />
            {saving ? 'Speichern…' : saved ? '✓ Gespeichert' : 'Speichern'}
          </button>
          <ModeBtn mode="edit" label="Bearbeiten" icon={Edit3} />
          <ModeBtn mode="split" label="Geteilt" icon={Columns} />
          <ModeBtn mode="preview" label="Vorschau" icon={Eye} />
        </div>
      )}

      {viewMode === 'preview' && (
        <div className="flex items-center justify-end gap-1 px-3 py-1 bg-gray-900 border-b border-gray-700 flex-shrink-0 print:hidden">
          <ModeBtn mode="edit" label="Bearbeiten" icon={Edit3} />
          <ModeBtn mode="split" label="Geteilt" icon={Columns} />
          <ModeBtn mode="preview" label="Vorschau" icon={Eye} />
        </div>
      )}

      {/* Content area */}
      <div className="flex flex-1 overflow-hidden">
        {/* Monaco Editor — always mounted (never unmounted) so editorRef stays valid in preview mode */}
        <div
          className="overflow-hidden print:hidden"
          style={{
            display: viewMode === 'preview' ? 'none' : 'block',
            width: viewMode === 'split' ? '50%' : '100%',
            borderRight: viewMode === 'split' ? '1px solid rgb(55,65,81)' : 'none',
            flexShrink: 0,
          }}
        >
          <Editor
            height="100%"
            language="markdown"
            theme="vs-dark"
            defaultValue=""
            onChange={val => setPreviewContent(val ?? '')}
            onMount={editor => {
              editorRef.current = editor
              editorRefCallback?.(editor)
              setupImagePaste(editor)
              const model = editor.getModel()
              if (model) {
                model.pushEditOperations([], [{
                  range: model.getFullModelRange(),
                  text: initialContent,
                }], () => null)
                editor.setPosition({ lineNumber: 1, column: 1 })
              }
            }}
            options={{
              fontSize: 13,
              fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
              wordWrap: 'on',
              minimap: { enabled: false },
              scrollBeyondLastLine: false,
              lineNumbers: 'off',
              folding: false,
              renderLineHighlight: 'none',
              padding: { top: 12, bottom: 12 },
              overviewRulerLanes: 0,
              hideCursorInOverviewRuler: true,
              scrollbar: { vertical: 'auto', horizontal: 'hidden' },
            }}
          />
        </div>

        {/* Preview */}
        {(viewMode === 'preview' || viewMode === 'split') && (
          <div className={`${viewMode === 'split' ? 'w-1/2' : 'w-full'} overflow-y-auto p-6 print:p-0`}>
            <article className={`max-w-none text-sm ${PROSE}`}>
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                rehypePlugins={[rehypeRaw]}
                urlTransform={(url) => url}
                components={{
                  img: ({ src, alt, width, height, style, ...rest }) => (
                    <img
                      src={src}
                      alt={alt ?? ''}
                      width={width}
                      height={height}
                      style={style as React.CSSProperties}
                      className="rounded border border-gray-700"
                      {...rest}
                    />
                  ),
                  h1: ({ children }) => { const t = String(children); return <h1 id={`heading-${headingSlug(t)}`}>{children}</h1> },
                  h2: ({ children }) => { const t = String(children); return <h2 id={`heading-${headingSlug(t)}`}>{children}</h2> },
                  h3: ({ children }) => { const t = String(children); return <h3 id={`heading-${headingSlug(t)}`}>{children}</h3> },
                  a: ({ href, children }) => (
                    <a
                      onClick={e => { e.preventDefault(); handleLinkClick(href) }}
                      href={href}
                      className="text-cyan-300 hover:text-cyan-200 underline underline-offset-2 cursor-pointer"
                    >
                      {children}
                    </a>
                  ),
                }}
              >
                {processedContent}
              </ReactMarkdown>
            </article>
          </div>
        )}
      </div>
    </div>
  )
}
