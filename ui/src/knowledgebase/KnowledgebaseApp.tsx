import { useCallback, useEffect, useRef, useState } from 'react'

const LS_TREE_W = 'kb_tree_width'
const LS_TOC_W  = 'kb_toc_width'
const MIN_W = 120
const MAX_W = 480

function useResizable(lsKey: string, defaultW: number) {
  const [width, setWidth] = useState(() => {
    const v = localStorage.getItem(lsKey)
    return v ? Math.max(MIN_W, Math.min(MAX_W, parseInt(v, 10))) : defaultW
  })
  const dragging = useRef(false)
  const startX   = useRef(0)
  const startW   = useRef(0)

  const onMouseDown = (e: React.MouseEvent) => {
    e.preventDefault()
    dragging.current = true
    startX.current   = e.clientX
    startW.current   = width

    const onMove = (ev: MouseEvent) => {
      if (!dragging.current) return
      const newW = Math.max(MIN_W, Math.min(MAX_W, startW.current + ev.clientX - startX.current))
      setWidth(newW)
    }
    const onUp = () => {
      dragging.current = false
      setWidth(w => { localStorage.setItem(lsKey, String(w)); return w })
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup',  onUp)
    }
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup',   onUp)
  }

  return { width, onMouseDown }
}
import { api, type KbDoc, type KbDocMeta, type KbSearchResult } from '@/api/client'
import { DocTree } from './components/DocTree'
import { KbEditor } from './components/KbEditor'
import { SearchPanel } from './components/SearchPanel'
import { TableOfContents } from './components/TableOfContents'
import {
  BookOpen, Search, Plus, FolderPlus, Download, Printer,
} from 'lucide-react'

export function KnowledgebaseApp() {
  const [docs, setDocs]           = useState<KbDocMeta[]>([])
  const [activeId, setActiveId]   = useState<string | null>(null)
  const [activeDoc, setActiveDoc] = useState<KbDoc | null>(null)
  const [initialContent, setInitialContent] = useState('')
  const [title, setTitle]         = useState('')
  const [saving, setSaving]       = useState(false)
  const [saved,  setSaved]        = useState(false)
  const [searchOpen, setSearchOpen] = useState(false)
  const [searchResults, setSearchResults] = useState<KbSearchResult[]>([])
  const [searchQuery, setSearchQuery] = useState('')

  const tree = useResizable(LS_TREE_W, 200)
  const toc  = useResizable(LS_TOC_W,  200)

  // Editor ref — read content on save without React state
  const editorRef  = useRef<{ getValue: () => string } | null>(null)
  const activeIdRef = useRef<string | null>(null)
  const titleRef    = useRef('')
  activeIdRef.current = activeId
  titleRef.current    = title

  const loadDocs = useCallback(async () => {
    const list = await api.kbListDocuments()
    setDocs(list)
  }, [])

  useEffect(() => { void loadDocs() }, [loadDocs])

  // Save reads content directly from Monaco — no state involved
  const saveNow = useCallback(async () => {
    const id = activeIdRef.current
    if (!id) return
    const currentContent = editorRef.current?.getValue() ?? ''
    setSaving(true)
    try {
      await api.kbUpdateDocument(id, { title: titleRef.current, content: currentContent })
      setSaved(true)
      setTimeout(() => setSaved(false), 1500)
      const list = await api.kbListDocuments()
      setDocs(list)
    } finally {
      setSaving(false)
    }
  }, [])

  const selectDoc = useCallback(async (id: string) => {
    const doc = await api.kbGetDocument(id)
    setActiveDoc(doc)
    setActiveId(id)
    setInitialContent(doc.content)
    setTitle(doc.title)
  }, [])

  const createDoc = async (parentId: string | null = null, isFolder = false) => {
    const result = await api.kbCreateDocument({
      title: isFolder ? 'Neuer Ordner' : 'Neues Dokument',
      is_folder: isFolder ? 1 : 0,
      parent_id: parentId,
    })
    await loadDocs()
    if (!isFolder) await selectDoc(result.id)
  }

  const moveDoc = async (id: string, newParentId: string | null) => {
    await api.kbUpdateDocument(id, { parent_id: newParentId })
    await loadDocs()
  }

  const deleteDoc = async (id: string) => {
    if (!confirm('Dokument wirklich löschen?')) return
    if (activeId === id) {
      setActiveId(null)
      setActiveDoc(null)
      setInitialContent('')
      setTitle('')
    }
    await api.kbDeleteDocument(id)
    await loadDocs()
  }

  const handleSearch = async (q: string) => {
    setSearchQuery(q)
    if (!q.trim()) { setSearchResults([]); return }
    const results = await api.kbSearch(q)
    setSearchResults(results)
  }

  const navigateTo = (id: string) => {
    setSearchOpen(false)
    void selectDoc(id)
  }

  const exportMarkdown = () => {
    if (!activeDoc) return
    const blob = new Blob([editorRef.current?.getValue() ?? initialContent], { type: 'text/markdown' })
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = `${title.replace(/[^a-z0-9]/gi, '_')}.md`
    a.click()
    URL.revokeObjectURL(a.href)
  }

  // Ctrl+S / Ctrl+K
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 's') { e.preventDefault(); void saveNow() }
      if ((e.ctrlKey || e.metaKey) && e.key === 'k') { e.preventDefault(); setSearchOpen(o => !o) }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [saveNow])

  return (
    <div className="flex flex-col h-screen overflow-hidden bg-gray-950 text-gray-200">
      {/* Top bar */}
      <div className="flex items-center gap-3 px-4 py-2 bg-gray-900 border-b border-gray-700 flex-shrink-0 print:hidden">
        <BookOpen className="w-4 h-4 text-emerald-400 flex-shrink-0" />
        <span className="text-sm font-semibold text-emerald-400">Knowledgebase</span>

        <div className="flex items-center gap-1 ml-2">
          <button onClick={() => createDoc(null, false)}
            className="flex items-center gap-1 text-xs px-2 py-1 rounded text-gray-400 hover:text-gray-200 hover:bg-gray-800 transition-colors"
            title="Neues Dokument">
            <Plus className="w-3.5 h-3.5" /> Dokument
          </button>
          <button onClick={() => createDoc(null, true)}
            className="flex items-center gap-1 text-xs px-2 py-1 rounded text-gray-400 hover:text-gray-200 hover:bg-gray-800 transition-colors"
            title="Neuer Ordner">
            <FolderPlus className="w-3.5 h-3.5" /> Ordner
          </button>
        </div>

        <div className="flex-1" />

        {activeDoc && !activeDoc.is_folder && (
          <>
            <button onClick={exportMarkdown}
              className="flex items-center gap-1 text-xs px-2 py-1 rounded text-gray-400 hover:text-gray-200 hover:bg-gray-800 transition-colors"
              title="Als Markdown exportieren">
              <Download className="w-3.5 h-3.5" /> MD
            </button>
            <button onClick={() => window.print()}
              className="flex items-center gap-1 text-xs px-2 py-1 rounded text-gray-400 hover:text-gray-200 hover:bg-gray-800 transition-colors"
              title="Drucken / Als PDF">
              <Printer className="w-3.5 h-3.5" /> PDF
            </button>
          </>
        )}

        <button onClick={() => setSearchOpen(o => !o)}
          className={`flex items-center gap-1 text-xs px-2 py-1 rounded transition-colors ${searchOpen ? 'bg-emerald-900/40 text-emerald-300' : 'text-gray-400 hover:text-gray-200 hover:bg-gray-800'}`}
          title="Suche (Ctrl+K)">
          <Search className="w-3.5 h-3.5" />
        </button>

      </div>

      {searchOpen && (
        <SearchPanel
          query={searchQuery}
          results={searchResults}
          onQuery={handleSearch}
          onNavigate={navigateTo}
          onClose={() => setSearchOpen(false)}
        />
      )}

      <div className="flex flex-1 overflow-hidden">
        {/* Ordnerstruktur */}
        <div className="flex-shrink-0 bg-gray-900 border-r border-gray-700 overflow-y-auto print:hidden"
          style={{ width: tree.width }}>
          <DocTree
            docs={docs}
            activeId={activeId}
            onSelect={selectDoc}
            onCreate={createDoc}
            onDelete={deleteDoc}
            onMove={moveDoc}
            onRename={async (id, newTitle) => {
              await api.kbUpdateDocument(id, { title: newTitle })
              await loadDocs()
              if (activeId === id) setTitle(newTitle)
            }}
          />
        </div>

        {/* Resize handle — Ordnerstruktur */}
        <div
          className="w-1 flex-shrink-0 bg-gray-700 hover:bg-emerald-500 cursor-col-resize transition-colors print:hidden"
          onMouseDown={tree.onMouseDown}
        />

        {/* Inhaltsverzeichnis */}
        <div className="flex-shrink-0 bg-gray-900 border-r border-gray-700 overflow-y-auto print:hidden"
          style={{ width: toc.width }}>
          <TableOfContents content={initialContent} />
        </div>

        {/* Resize handle — Inhaltsverzeichnis */}
        <div
          className="w-1 flex-shrink-0 bg-gray-700 hover:bg-emerald-500 cursor-col-resize transition-colors print:hidden"
          onMouseDown={toc.onMouseDown}
        />

        {/* Editor */}
        <div className="flex-1 flex flex-col overflow-hidden">
          {activeDoc && !activeDoc.is_folder ? (
            <KbEditor
              docId={activeId ?? ''}
              title={title}
              initialContent={initialContent}
              onTitleChange={val => setTitle(val)}
              onSave={() => void saveNow()}
              saving={saving}
              saved={saved}
              docs={docs}
              onNavigate={navigateTo}
              editorRefCallback={r => { editorRef.current = r }}
            />
          ) : (
            <div className="flex-1 flex items-center justify-center text-gray-600 text-sm">
              {docs.length === 0
                ? 'Kein Dokument vorhanden — erstelle eines mit "+ Dokument"'
                : 'Dokument auswählen'}
            </div>
          )}
        </div>
      </div>

      <style>{`
        @media print {
          body { background: white !important; color: black !important; }
          .print\\:hidden { display: none !important; }
        }
      `}</style>
    </div>
  )
}
