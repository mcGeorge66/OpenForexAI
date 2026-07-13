import { useEffect, useRef, useState } from 'react'
import { ChevronRight, Edit2, Home, RefreshCw, Save, X } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { api } from '@/api/client'

interface HistoryEntry {
  filename: string
  title: string
}

function extractTitle(text: string, filename: string): string {
  const m = text.match(/^#\s+(.+)/m)
  return m ? m[1].trim() : filename
}

function headingSlug(text: string): string {
  return text.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '')
}

export function HandbookView() {
  const initialFile = new URLSearchParams(window.location.search).get('file') ?? 'README.md'
  const [history, setHistory] = useState<HistoryEntry[]>([])
  const [current, setCurrent] = useState<string>(initialFile)
  const [text, setText] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [editMode, setEditMode] = useState(false)
  const [editText, setEditText] = useState('')
  const [saving, setSaving] = useState(false)
  const [saveMsg, setSaveMsg] = useState<string | null>(null)
  const [lightboxSrc, setLightboxSrc] = useState<string | null>(null)
  const pendingAnchorRef = useRef<string | null>(null)

  const loadFile = (filename: string, addToHistory: boolean, prevTitle?: string) => {
    setLoading(true)
    setError(null)
    setSaveMsg(null)
    setEditMode(false)
    api.getDocFile(filename)
      .then(raw => {
        if (addToHistory && prevTitle !== undefined) {
          setHistory(h => [...h, { filename: current, title: prevTitle }])
        }
        setCurrent(filename)
        setText(raw)
        setLoading(false)
      })
      .catch(err => {
        setError(String(err))
        setLoading(false)
      })
  }

  useEffect(() => {
    loadFile(initialFile, false)
  }, [])

  useEffect(() => {
    const anchor = pendingAnchorRef.current
    if (!anchor) return
    pendingAnchorRef.current = null
    setTimeout(() => {
      document.getElementById(anchor)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    }, 50)
  }, [text])

  const navigateTo = (filename: string) => {
    const currentTitle = extractTitle(text, current)
    loadFile(filename, true, currentTitle)
  }

  const navigateBack = (index: number) => {
    const entry = history[index]
    setHistory(h => h.slice(0, index))
    loadFile(entry.filename, false)
  }

  const handleEdit = () => {
    setEditText(text)
    setEditMode(true)
    setSaveMsg(null)
  }

  const handleCancelEdit = () => {
    setEditMode(false)
    setSaveMsg(null)
  }

  const handleSave = async () => {
    setSaving(true)
    setSaveMsg(null)
    try {
      await api.saveDocFile(current, editText)
      setText(editText)
      setEditMode(false)
      setSaveMsg('Saved.')
    } catch (err) {
      setSaveMsg(`Error: ${String(err)}`)
    } finally {
      setSaving(false)
    }
  }

  const currentTitle = text ? extractTitle(text, current) : current

  const IMAGE_EXTS = /\.(png|jpe?g|gif|webp|svg|bmp)(\?.*)?$/i

  const handleLinkClick = (href: string | undefined) => {
    if (!href) return

    // Pure anchor → same-page scroll
    if (href.startsWith('#')) {
      document.getElementById(href.slice(1))?.scrollIntoView({ behavior: 'smooth', block: 'start' })
      return
    }

    // Full URL → check if same origin with handbook params
    if (href.startsWith('http://') || href.startsWith('https://')) {
      try {
        const url = new URL(href)
        const file = url.searchParams.get('file')
        const anchor = url.hash.slice(1)
        if (url.origin === window.location.origin && file) {
          if (file === current) {
            if (anchor) document.getElementById(anchor)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
          } else {
            if (anchor) pendingAnchorRef.current = anchor
            navigateTo(file)
          }
          return
        }
      } catch { /* ignore malformed URLs */ }
      // External link → new tab
      window.open(href, '_blank', 'noopener,noreferrer')
      return
    }

    // Internal .md link with optional anchor
    const mdMatch = href.match(/^(?:\.\/)?([^#]+\.md)(?:#(.+))?$/)
    if (mdMatch) {
      const filename = mdMatch[1].replace(/^.*\//, '')
      const anchor = mdMatch[2]
      if (filename === current && anchor) {
        document.getElementById(anchor)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
      } else {
        if (anchor) pendingAnchorRef.current = anchor
        navigateTo(filename)
      }
      return
    }

    // Image link → lightbox
    if (IMAGE_EXTS.test(href)) {
      setLightboxSrc(href)
      return
    }

    // External link → new tab
    window.open(href, '_blank', 'noopener,noreferrer')
  }

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center gap-2 px-4 py-2 bg-gray-900 border-b border-gray-700 flex-shrink-0 flex-wrap">
        <button
          onClick={() => loadFile(initialFile, false)}
          className="flex items-center gap-1 text-xs text-gray-400 hover:text-gray-200 transition-colors"
          title="Go to start"
        >
          <Home className="w-3.5 h-3.5" />
        </button>
        {history.map((entry, i) => (
          <span key={i} className="flex items-center gap-2">
            <ChevronRight className="w-3 h-3 text-gray-600 flex-shrink-0" />
            <button
              onClick={() => navigateBack(i)}
              className="text-xs text-cyan-400 hover:text-cyan-200 transition-colors truncate max-w-[160px]"
              title={entry.title}
            >
              {entry.title}
            </button>
          </span>
        ))}
        {history.length > 0 && (
          <span className="flex items-center gap-2">
            <ChevronRight className="w-3 h-3 text-gray-600 flex-shrink-0" />
            <span className="text-xs text-gray-300 truncate max-w-[200px]">{currentTitle}</span>
          </span>
        )}

        <div className="ml-auto flex items-center gap-2">
          {saveMsg && (
            <span className={`text-xs ${saveMsg.startsWith('Error') ? 'text-red-400' : 'text-emerald-400'}`}>
              {saveMsg}
            </span>
          )}
          {editMode ? (
            <>
              <button
                onClick={() => void handleSave()}
                disabled={saving}
                className="flex items-center gap-1 text-xs px-2 py-1 rounded bg-emerald-700 hover:bg-emerald-600 text-white disabled:opacity-50"
              >
                {saving ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />}
                {saving ? 'Saving…' : 'Save'}
              </button>
              <button
                onClick={handleCancelEdit}
                className="flex items-center gap-1 text-xs px-2 py-1 rounded border border-gray-600 text-gray-300 hover:bg-gray-800"
              >
                <X className="w-3.5 h-3.5" />
                Cancel
              </button>
            </>
          ) : (
            <>
              <button
                onClick={handleEdit}
                disabled={loading || !text}
                className="flex items-center gap-1 text-xs px-2 py-1 rounded border border-gray-600 text-gray-300 hover:bg-gray-800 disabled:opacity-40"
                title="Edit this file"
              >
                <Edit2 className="w-3.5 h-3.5" />
                Edit
              </button>
              <button
                onClick={() => loadFile(current, false)}
                disabled={loading}
                className="flex items-center gap-1 text-xs text-gray-400 hover:text-gray-200 transition-colors disabled:opacity-40"
                title="Reload file"
              >
                <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
              </button>
            </>
          )}
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-auto p-4 bg-gray-950">
        {loading && <p className="text-gray-500 text-sm animate-pulse">Loading…</p>}
        {error && <p className="text-red-400 text-sm">Error: {error}</p>}
        {!loading && !error && editMode && (
          <textarea
            value={editText}
            onChange={e => setEditText(e.target.value)}
            className="w-full h-full min-h-[70vh] bg-gray-900 border border-gray-700 rounded px-3 py-2 text-sm text-gray-200 font-mono resize-none focus:outline-none focus:border-gray-500"
            spellCheck={false}
          />
        )}
        {!loading && !error && !editMode && (
          <article
            className={[
              'max-w-none text-sm text-gray-200 leading-7',
              '[&_h1]:text-3xl [&_h1]:font-semibold [&_h1]:text-white [&_h1]:mt-6 [&_h1]:mb-4 [&_h1]:border-b [&_h1]:border-gray-700 [&_h1]:pb-2',
              '[&_h2]:text-2xl [&_h2]:font-semibold [&_h2]:text-white [&_h2]:mt-6 [&_h2]:mb-3',
              '[&_h3]:text-xl [&_h3]:font-semibold [&_h3]:text-gray-100 [&_h3]:mt-5 [&_h3]:mb-2',
              '[&_h4]:text-lg [&_h4]:font-semibold [&_h4]:text-gray-100 [&_h4]:mt-4 [&_h4]:mb-2',
              '[&_p]:my-3 [&_p]:text-gray-300',
              '[&_ul]:list-disc [&_ul]:pl-6 [&_ul]:my-3',
              '[&_ol]:list-decimal [&_ol]:pl-6 [&_ol]:my-3',
              '[&_li]:my-1 [&_li]:text-gray-300',
              '[&_a]:text-cyan-300 hover:[&_a]:text-cyan-200 [&_a]:underline [&_a]:underline-offset-2 [&_a]:cursor-pointer',
              '[&_blockquote]:border-l-4 [&_blockquote]:border-gray-600 [&_blockquote]:pl-4 [&_blockquote]:italic [&_blockquote]:text-gray-400 [&_blockquote]:my-4',
              '[&_code]:font-mono [&_code]:text-emerald-300 [&_code]:bg-gray-900 [&_code]:px-1.5 [&_code]:py-0.5 [&_code]:rounded',
              '[&_pre]:bg-gray-900 [&_pre]:border [&_pre]:border-gray-700 [&_pre]:rounded [&_pre]:p-3 [&_pre]:overflow-auto [&_pre]:my-4',
              '[&_pre_code]:bg-transparent [&_pre_code]:p-0 [&_pre_code]:rounded-none',
              '[&_table]:w-full [&_table]:border-collapse [&_table]:my-4 [&_table]:text-sm',
              '[&_thead_th]:text-left [&_thead_th]:text-gray-200 [&_thead_th]:font-semibold [&_thead_th]:border-b [&_thead_th]:border-gray-600 [&_thead_th]:px-3 [&_thead_th]:py-2',
              '[&_tbody_td]:border-b [&_tbody_td]:border-gray-800 [&_tbody_td]:px-3 [&_tbody_td]:py-2 [&_tbody_td]:text-gray-300',
              '[&_hr]:border-gray-700 [&_hr]:my-6',
            ].join(' ')}
          >
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={{
                a: ({ href, children }) => (
                  <a
                    onClick={e => { e.preventDefault(); handleLinkClick(href) }}
                    href={href}
                    className="text-cyan-300 hover:text-cyan-200 underline underline-offset-2 cursor-pointer"
                  >
                    {children}
                  </a>
                ),
                h1: ({ children }) => <h1 id={headingSlug(String(children))}>{children}</h1>,
                h2: ({ children }) => <h2 id={headingSlug(String(children))}>{children}</h2>,
                h3: ({ children }) => <h3 id={headingSlug(String(children))}>{children}</h3>,
                h4: ({ children }) => <h4 id={headingSlug(String(children))}>{children}</h4>,
              }}
            >
              {text}
            </ReactMarkdown>
          </article>
        )}
      </div>
      {/* Lightbox */}
      {lightboxSrc && (
        <LightboxModal src={lightboxSrc} onClose={() => setLightboxSrc(null)} />
      )}
    </div>
  )
}

// ─── Image with fallback ──────────────────────────────────────────────────────

function ImageWithFallback({ src }: { src: string }) {
  const [failed, setFailed] = useState(false)
  if (failed) {
    return (
      <div className="flex flex-col items-center gap-2 px-8 py-6 rounded border border-gray-700 bg-gray-900 text-gray-500 text-sm">
        <span className="text-2xl">🖼️</span>
        <span>Image not found</span>
        <span className="text-xs text-gray-600 font-mono break-all max-w-sm text-center">{src}</span>
        <span className="text-xs text-gray-600 mt-1">Place the file in <code className="text-gray-400">ui/public/{src}</code> and rebuild.</span>
      </div>
    )
  }
  return (
    <img
      src={src}
      alt=""
      className="max-w-[90vw] max-h-[90vh] rounded border border-gray-700 shadow-2xl object-contain"
      onError={() => setFailed(true)}
    />
  )
}

// ─── Lightbox ─────────────────────────────────────────────────────────────────

function LightboxModal({ src, onClose }: { src: string; onClose: () => void }) {
  const backdropRef = useRef<HTMLDivElement>(null)

  // Close on Escape
  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onClose])

  return (
    <div
      ref={backdropRef}
      className="fixed inset-0 z-[300] flex items-center justify-center bg-black/80 backdrop-blur-sm p-6"
      onClick={e => { if (e.target === backdropRef.current) onClose() }}
    >
      <div className="relative max-w-[90vw] max-h-[90vh]">
        <button
          onClick={onClose}
          className="absolute -top-3 -right-3 z-10 flex items-center justify-center w-7 h-7 rounded-full bg-gray-800 border border-gray-600 text-gray-300 hover:text-white hover:bg-gray-700 transition-colors"
          title="Close"
        >
          <X className="w-4 h-4" />
        </button>
        <ImageWithFallback src={src} />
      </div>
    </div>
  )
}
