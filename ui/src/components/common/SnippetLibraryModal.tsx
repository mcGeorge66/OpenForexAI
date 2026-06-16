import { useEffect, useRef, useState } from 'react'
import MonacoEditor from '@monaco-editor/react'
import type { editor as MonacoEditorNS } from 'monaco-editor'
import { Check, Code, Copy, CopyPlus, Plus, Save, Search, Trash2, X } from 'lucide-react'
import { api, type SnippetLibraryEntry, type SnippetLibrary } from '@/api/client'

// ── helpers ───────────────────────────────────────────────────────────────────

function newId(): string {
  return Date.now().toString(36) + Math.random().toString(36).slice(2)
}

function newEntry(): SnippetLibraryEntry {
  return { id: newId(), name: '', version: '1', description: '', tags: '', code: '' }
}

function parseVer(v: string): number {
  const n = parseFloat(v)
  return isNaN(n) ? 0 : n
}

function nextVersion(entries: SnippetLibraryEntry[], name: string): string {
  const siblings = entries.filter(e => e.name.trim().toLowerCase() === name.trim().toLowerCase())
  if (siblings.length === 0) return '1'
  const max = Math.max(...siblings.map(e => parseVer(e.version)))
  return String(Math.floor(isFinite(max) ? max : 0) + 1)
}

function sortedEntries(entries: SnippetLibraryEntry[]): SnippetLibraryEntry[] {
  return [...entries].sort((a, b) => {
    const nc = a.name.localeCompare(b.name, undefined, { sensitivity: 'base' })
    if (nc !== 0) return nc
    return parseVer(a.version) - parseVer(b.version)
  })
}

// ── Mini search-query engine ──────────────────────────────────────────────────
// Grammar:
//   query    = or_expr
//   or_expr  = and_expr ('OR' and_expr)*
//   and_expr = not_expr ('AND'? not_expr)*     ← space = implicit AND
//   not_expr = ('NOT' | '-') atom | atom
//   atom     = TERM | '(' or_expr ')'
//
// TERM wildcards: Close* startsWith, *calc endsWith, *foo* substring (word-level)
// Fallback on parse error: plain substring across all fields.

type MatchFn = (text: string) => boolean

function _termPred(raw: string): MatchFn {
  const s = raw.toLowerCase()
  if (s === '*') return () => true
  const leading  = s.startsWith('*')
  const trailing = s.endsWith('*')
  const core = s.replace(/^\*+/, '').replace(/\*+$/, '')
  if (!core) return () => true
  // no wildcard → plain substring anywhere in text
  if (!leading && !trailing) return (t: string) => t.includes(core)
  // *core* → any word contains core
  if (leading && trailing) return (t: string) => t.split(/[\s,/]+/).some(w => w.includes(core))
  // *core → any word ends with core
  if (leading) return (t: string) => t.split(/[\s,/]+/).some(w => w.endsWith(core))
  // core* → any word starts with core
  return (t: string) => t.split(/[\s,/]+/).some(w => w.startsWith(core))
}

type TokKind = 'TERM' | 'AND' | 'OR' | 'NOT' | 'LP' | 'RP'
type Tok = { k: TokKind; v: string }

function _lex(q: string): Tok[] {
  const out: Tok[] = []
  let i = 0
  while (i < q.length) {
    if (q[i] === ' ') { i++; continue }
    if (q[i] === '(') { out.push({ k: 'LP', v: '(' }); i++; continue }
    if (q[i] === ')') { out.push({ k: 'RP', v: ')' }); i++; continue }
    const neg = q[i] === '-'
    if (neg) i++
    let w = ''
    while (i < q.length && !/[ ()]/.test(q[i])) w += q[i++]
    if (!w) continue
    if (neg) { out.push({ k: 'NOT', v: 'NOT' }); out.push({ k: 'TERM', v: w }); continue }
    const up = w.toUpperCase()
    if      (up === 'AND') out.push({ k: 'AND', v: w })
    else if (up === 'OR')  out.push({ k: 'OR',  v: w })
    else if (up === 'NOT') out.push({ k: 'NOT', v: w })
    else                   out.push({ k: 'TERM', v: w })
  }
  return out
}

function buildFilter(query: string): (e: SnippetLibraryEntry) => boolean {
  const q = query.trim()
  if (!q) return () => true
  try {
    const toks = _lex(q)
    let pos = 0
    const peek = (): Tok | undefined => toks[pos]
    const next = (): Tok => toks[pos++]

    function orExpr(): MatchFn {
      let l = andExpr()
      while (peek()?.k === 'OR') {
        next()
        const r = andExpr()
        const lp = l;  l = t => lp(t) || r(t)
      }
      return l
    }

    function andExpr(): MatchFn {
      let l = notExpr()
      while (true) {
        const p = peek()
        if (!p || p.k === 'OR' || p.k === 'RP') break
        if (p.k === 'AND') next()
        const p2 = peek()
        if (!p2 || p2.k === 'OR' || p2.k === 'RP') break
        const r = notExpr()
        const lp = l;  l = t => lp(t) && r(t)
      }
      return l
    }

    function notExpr(): MatchFn {
      if (peek()?.k === 'NOT') { next(); const r = atom(); return t => !r(t) }
      return atom()
    }

    function atom(): MatchFn {
      const tok = peek()
      if (!tok) return () => true
      if (tok.k === 'LP') { next(); const r = orExpr(); if (peek()?.k === 'RP') next(); return r }
      if (tok.k === 'TERM') { next(); return _termPred(tok.v) }
      next(); return () => true
    }

    const pred = orExpr()
    return e => {
      const text = `${e.name} ${e.description ?? ''} ${e.tags ?? ''}`.toLowerCase()
      return pred(text)
    }
  } catch {
    const lc = q.toLowerCase()
    return e => `${e.name} ${e.description ?? ''} ${e.tags ?? ''}`.toLowerCase().includes(lc)
  }
}

// ─────────────────────────────────────────────────────────────────────────────

function CopyButton({ getText }: { getText: () => string }) {
  const [copied, setCopied] = useState(false)
  return (
    <button
      type="button"
      title="Copy to clipboard"
      onClick={() => {
        void navigator.clipboard.writeText(getText()).then(() => {
          setCopied(true)
          setTimeout(() => setCopied(false), 1500)
        })
      }}
      className="inline-flex items-center text-gray-500 hover:text-gray-300 transition-colors"
    >
      {copied ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
    </button>
  )
}

// ── types ─────────────────────────────────────────────────────────────────────

export interface SnippetLibraryModalProps {
  scope: string
  /** Called with the snippet code to insert at the current cursor position */
  onInsert: (code: string) => void
  onClose: () => void
}

// ── component ─────────────────────────────────────────────────────────────────

export function SnippetLibraryModal({ scope, onInsert, onClose }: SnippetLibraryModalProps) {
  const editorRef = useRef<MonacoEditorNS.IStandaloneCodeEditor | null>(null)

  const [entries, setEntries]       = useState<SnippetLibraryEntry[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [draft, setDraft]           = useState<SnippetLibraryEntry | null>(null)
  const [loading, setLoading]       = useState(true)
  const [saving, setSaving]         = useState(false)
  const [error, setError]           = useState<string | null>(null)
  const [message, setMessage]       = useState<string | null>(null)
  const [filter, setFilter]         = useState('')

  // ── load on mount ───────────────────────────────────────────────────────────

  useEffect(() => {
    setLoading(true)
    api.getSnippetLibrary(scope)
      .then((lib: SnippetLibrary) => {
        const snips = lib.snippets ?? []
        setEntries(snips)
        if (snips.length > 0) {
          const first = sortedEntries(snips)[0]
          setSelectedId(first.id)
          setDraft({ ...first })
        }
        setLoading(false)
      })
      .catch((e: unknown) => {
        setError(String(e))
        setLoading(false)
      })
  }, [scope])

  // ── handlers ────────────────────────────────────────────────────────────────

  function selectEntry(entry: SnippetLibraryEntry) {
    setSelectedId(entry.id)
    setDraft({ ...entry })
    setMessage(null)
  }

  function handleNew() {
    const e = newEntry()
    setSelectedId(e.id)
    setDraft(e)
    setMessage(null)
    setError(null)
  }

  async function handleSave() {
    if (!draft) return
    if (!draft.name.trim()) { setError('Name is required.'); return }
    setSaving(true)
    setError(null)
    const isNew = !entries.find(e => e.id === draft.id)
    const next = isNew
      ? [...entries, draft]
      : entries.map(e => e.id === draft.id ? draft : e)
    try {
      await api.saveSnippetLibrary(scope, { snippets: next })
      setEntries(next)
      setMessage('Saved.')
      setTimeout(() => setMessage(null), 2000)
    } catch (e: unknown) {
      setError(String(e))
    } finally {
      setSaving(false)
    }
  }

  async function handleDelete() {
    if (!draft) return
    const next = entries.filter(e => e.id !== draft.id)
    setSaving(true)
    setError(null)
    try {
      await api.saveSnippetLibrary(scope, { snippets: next })
      setEntries(next)
      const sorted = sortedEntries(next)
      if (sorted.length > 0) {
        setSelectedId(sorted[0].id)
        setDraft({ ...sorted[0] })
      } else {
        setSelectedId(null)
        setDraft(null)
      }
      setMessage('Deleted.')
      setTimeout(() => setMessage(null), 2000)
    } catch (e: unknown) {
      setError(String(e))
    } finally {
      setSaving(false)
    }
  }

  function handleDuplicate() {
    if (!draft) return
    const copy: SnippetLibraryEntry = {
      ...draft,
      id: newId(),
      version: nextVersion(entries, draft.name),
    }
    setSelectedId(copy.id)
    setDraft(copy)
    setMessage(null)
    setError(null)
  }

  function patchDraft(patch: Partial<SnippetLibraryEntry>) {
    setDraft(prev => prev ? { ...prev, ...patch } : prev)
  }

  function handleCodeChange(value: string | undefined) {
    patchDraft({ code: value ?? '' })
  }

  // ── render ──────────────────────────────────────────────────────────────────

  return (
    <div className="fixed inset-0 z-[300] bg-black/75 flex items-center justify-center p-6">
      <div className="w-full max-w-5xl max-h-[90vh] bg-gray-950 border border-gray-700 rounded-xl overflow-hidden flex flex-col">

        {/* Header */}
        <div className="px-5 py-3 border-b border-gray-800 flex items-center justify-between flex-shrink-0">
          <div className="flex items-center gap-2">
            <Code className="w-4 h-4 text-gray-400" />
            <span className="text-sm font-semibold text-gray-100">Snippet Library</span>
          </div>
          <button onClick={onClose} className="text-gray-500 hover:text-gray-200 transition-colors">
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 min-h-0 flex overflow-hidden">

          {/* Left — entry list */}
          <div className="w-64 flex-shrink-0 border-r border-gray-800 flex flex-col">
            <div className="px-2 py-2 border-b border-gray-800 flex-shrink-0 flex flex-col gap-1.5">
              <div className="flex items-center gap-1.5">
                <button
                  onClick={handleNew}
                  title="New Snippet"
                  className="flex-shrink-0 flex items-center justify-center gap-1 px-2 py-1.5 rounded bg-emerald-700 hover:bg-emerald-600 text-white text-xs"
                >
                  <Plus className="w-3.5 h-3.5" />
                  New
                </button>
                <div className="relative flex-1 min-w-0">
                  <Search className="absolute left-2 top-1/2 -translate-y-1/2 w-3 h-3 text-gray-500 pointer-events-none" />
                  <input
                    type="text"
                    value={filter}
                    onChange={e => setFilter(e.target.value)}
                    placeholder="Filter… (rsi OR trend, Close*, -entry)"
                    className="w-full bg-gray-800 border border-gray-600 rounded pl-6 pr-2 py-1 text-xs text-gray-200 placeholder-gray-600 focus:outline-none focus:border-gray-500"
                  />
                </div>
              </div>
              {filter.trim() && (
                <p className="text-[9px] text-gray-600 px-1 leading-tight">
                  Suche in Name · Beschreibung · Tags &nbsp;|&nbsp; Operatoren: AND &nbsp;OR &nbsp;NOT &nbsp;- &nbsp;* &nbsp;( )
                </p>
              )}
            </div>

            <div className="flex-1 overflow-y-auto">
              {loading && (
                <p className="px-3 py-3 text-xs text-gray-500 animate-pulse">Loading…</p>
              )}
              {!loading && entries.length === 0 && (
                <p className="px-3 py-3 text-xs text-gray-500">No snippets yet. Click "New" to start.</p>
              )}
              {(() => {
                const pred = buildFilter(filter)
                const visible = sortedEntries(entries).filter(pred)
                if (!loading && entries.length > 0 && visible.length === 0) {
                  return <p className="px-3 py-3 text-xs text-gray-500">Keine Treffer für „{filter.trim()}"</p>
                }
                return visible.map(entry => (
                  <button
                    key={entry.id}
                    onClick={() => selectEntry(entry)}
                    className={`w-full text-left px-3 py-2.5 border-b border-gray-800/60 hover:bg-gray-900 transition-colors ${
                      selectedId === entry.id ? 'bg-gray-800 border-l-2 border-l-emerald-500' : ''
                    }`}
                  >
                    <div className="flex items-baseline gap-1.5 min-w-0">
                      <span className="text-xs text-gray-200 font-medium truncate flex-1">
                        {entry.name || <span className="text-gray-500 italic">Unnamed</span>}
                      </span>
                      {entry.version && (
                        <span className="flex-shrink-0 text-[10px] text-emerald-500 font-mono">v{entry.version}</span>
                      )}
                    </div>
                    {entry.description && (
                      <div className="text-[11px] text-gray-500 mt-0.5 truncate">{entry.description}</div>
                    )}
                    {entry.tags && (
                      <div className="flex flex-wrap gap-1 mt-0.5">
                        {entry.tags.split(',').map(t => t.trim()).filter(Boolean).map(t => (
                          <span key={t} className="text-[9px] px-1 py-px rounded bg-gray-700 text-gray-400 font-mono">{t}</span>
                        ))}
                      </div>
                    )}
                  </button>
                ))
              })()}
            </div>
          </div>

          {/* Right — editor */}
          <div className="flex-1 min-h-0 flex flex-col p-4 gap-3 overflow-y-auto">
            {!draft && (
              <p className="text-xs text-gray-500 mt-6 text-center">Select a snippet from the list or create a new one.</p>
            )}

            {draft && (
              <>
                {/* Row: Name + Version + actions */}
                <div className="flex items-end gap-2 flex-shrink-0">
                  <label className="flex-1 text-xs text-gray-400">
                    Name
                    <input
                      value={draft.name}
                      onChange={e => patchDraft({ name: e.target.value })}
                      className="mt-0.5 w-full bg-gray-800 border border-gray-600 rounded px-2 py-1 text-sm text-gray-200"
                      placeholder="E.g. Normalize candles"
                    />
                  </label>
                  <label className="w-20 text-xs text-gray-400 flex-shrink-0">
                    Version
                    <input
                      value={draft.version}
                      onChange={e => patchDraft({ version: e.target.value })}
                      className="mt-0.5 w-full bg-gray-800 border border-gray-600 rounded px-2 py-1 text-sm text-gray-200 font-mono"
                      placeholder="1"
                    />
                  </label>
                  <div className="flex items-center gap-1.5 pb-0.5">
                    <button
                      onClick={() => void handleSave()}
                      disabled={saving}
                      className="flex items-center gap-1 px-2.5 py-1 rounded bg-emerald-700 hover:bg-emerald-600 text-white text-xs disabled:opacity-50"
                    >
                      <Save className="w-3 h-3" />
                      Save
                    </button>
                    <button
                      onClick={handleDuplicate}
                      disabled={saving}
                      title="Duplicate — creates an unsaved copy; adjust name or version, then Save"
                      className="flex items-center gap-1 px-2.5 py-1 rounded bg-blue-700 hover:bg-blue-600 text-white text-xs disabled:opacity-50"
                    >
                      <CopyPlus className="w-3 h-3" />
                      Duplicate
                    </button>
                    <button
                      onClick={() => void handleDelete()}
                      disabled={saving || !entries.find(e => e.id === draft.id)}
                      className="flex items-center gap-1 px-2.5 py-1 rounded bg-red-700 hover:bg-red-600 text-white text-xs disabled:opacity-50"
                    >
                      <Trash2 className="w-3 h-3" />
                      Delete
                    </button>
                  </div>
                </div>

                {/* Description */}
                <label className="block text-xs text-gray-400 flex-shrink-0">
                  Description
                  <textarea
                    rows={3}
                    value={draft.description}
                    onChange={e => patchDraft({ description: e.target.value })}
                    className="mt-0.5 w-full bg-gray-800 border border-gray-600 rounded px-2 py-1 text-sm text-gray-200 resize-y"
                    placeholder="What does this snippet do?"
                  />
                </label>

                {/* Tags */}
                <label className="block text-xs text-gray-400 flex-shrink-0">
                  Tags
                  <input
                    type="text"
                    value={draft.tags ?? ''}
                    onChange={e => patchDraft({ tags: e.target.value })}
                    className="mt-0.5 w-full bg-gray-800 border border-gray-600 rounded px-2 py-1 text-sm text-gray-200"
                    placeholder="E.g. SnapshotCalc, Indicator"
                  />
                  <span className="text-[10px] text-gray-600">Comma-separated keywords. Used for filtering (e.g. SnapshotCalc).</span>
                </label>

                {/* Code — Monaco Editor */}
                <div className="flex-1 min-h-0 flex flex-col">
                  <div className="flex items-center justify-between mb-1 flex-shrink-0">
                    <span className="text-xs text-gray-400">Code</span>
                    <CopyButton getText={() => draft.code} />
                  </div>
                  <div className="flex-1 min-h-[280px] rounded border border-gray-600 overflow-hidden">
                    <MonacoEditor
                      height="100%"
                      defaultLanguage="python"
                      theme="vs-dark"
                      value={draft.code}
                      onChange={handleCodeChange}
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
                        scrollbar: { vertical: 'auto', horizontal: 'auto' },
                        overviewRulerLanes: 0,
                        renderLineHighlight: 'line',
                      }}
                    />
                  </div>
                </div>
              </>
            )}

            {/* Status messages */}
            {message && <p className="text-xs text-emerald-400 flex-shrink-0">{message}</p>}
            {error   && <p className="text-xs text-red-400 flex-shrink-0">{error}</p>}
          </div>
        </div>

        {/* Footer */}
        <div className="px-5 py-3 border-t border-gray-800 flex items-center justify-between flex-shrink-0 bg-gray-900/40">
          <button
            onClick={onClose}
            className="px-3 py-1.5 rounded border border-gray-700 bg-gray-900 text-gray-300 hover:text-white text-sm"
          >
            Close
          </button>
          <button
            onClick={() => { if (draft?.code) { onInsert(draft.code); onClose() } }}
            disabled={!draft?.code}
            title="Insert this snippet at the current cursor position in the script"
            className="px-3 py-1.5 rounded border border-emerald-700 bg-emerald-900/40 text-emerald-300 hover:bg-emerald-800/60 text-sm disabled:opacity-40 disabled:cursor-not-allowed"
          >
            Insert at Cursor
          </button>
        </div>

      </div>
    </div>
  )
}
