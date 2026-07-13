import { useEffect, useState } from 'react'
import { BookOpen, Check, Copy, CopyPlus, Maximize2, Plus, Save, Trash2, X } from 'lucide-react'
import { api, type PromptLibraryEntry, type PromptLibrary } from '@/api/client'

// ── helpers ───────────────────────────────────────────────────────────────────

function newId(): string {
  return Date.now().toString(36) + Math.random().toString(36).slice(2)
}

function newEntry(): PromptLibraryEntry {
  return { id: newId(), name: '', version: '1', description: '', text: '' }
}

/** Numeric-aware version parse — falls back to 0 for non-numeric strings. */
function parseVer(v: string): number {
  const n = parseFloat(v)
  return isNaN(n) ? 0 : n
}

/** Next integer version for a given name: max existing numeric version + 1. */
function nextVersion(entries: PromptLibraryEntry[], name: string): string {
  const siblings = entries.filter(e => e.name.trim().toLowerCase() === name.trim().toLowerCase())
  if (siblings.length === 0) return '1'
  const max = Math.max(...siblings.map(e => parseVer(e.version)))
  return String(Math.floor(isFinite(max) ? max : 0) + 1)
}

/** Sort entries: name ascending (case-insensitive), then version ascending (numeric-aware). */
function sortedEntries(entries: PromptLibraryEntry[]): PromptLibraryEntry[] {
  return [...entries].sort((a, b) => {
    const nc = a.name.localeCompare(b.name, undefined, { sensitivity: 'base' })
    if (nc !== 0) return nc
    return parseVer(a.version) - parseVer(b.version)
  })
}

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

export interface PromptLibraryModalProps {
  /** 'agent' → prompt_library_agent.json5 · 'decision' → prompt_library_decision.json5 */
  scope: string
  /** Called when the modal should close */
  onClose: () => void
  /** Called when the user clicks "Insert" — append text to existing prompt */
  onInsert: (text: string) => void
  /** Called when the user clicks "Replace" — overwrite existing prompt */
  onReplace: (text: string) => void
}

// ── component ─────────────────────────────────────────────────────────────────

export function PromptLibraryModal({ scope, onClose, onInsert, onReplace }: PromptLibraryModalProps) {
  const [entries, setEntries]       = useState<PromptLibraryEntry[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [draft, setDraft]           = useState<PromptLibraryEntry | null>(null)
  const [loading, setLoading]       = useState(true)
  const [saving, setSaving]         = useState(false)
  const [error, setError]           = useState<string | null>(null)
  const [message, setMessage]       = useState<string | null>(null)
  const [promptExpanded, setPromptExpanded] = useState(false)

  // ── load on mount ───────────────────────────────────────────────────────────

  useEffect(() => {
    setLoading(true)
    api.getPromptLibrary(scope)
      .then((lib: PromptLibrary) => {
        const prompts = lib.prompts ?? []
        setEntries(prompts)
        // auto-select first entry (sorted order)
        if (prompts.length > 0) {
          const first = sortedEntries(prompts)[0]
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

  function selectEntry(entry: PromptLibraryEntry) {
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
      await api.savePromptLibrary(scope, { prompts: next })
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
      await api.savePromptLibrary(scope, { prompts: next })
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
    const copy: PromptLibraryEntry = {
      ...draft,
      id: newId(),
      version: nextVersion(entries, draft.name),
    }
    setSelectedId(copy.id)
    setDraft(copy)
    setMessage(null)
    setError(null)
  }

  function patchDraft(patch: Partial<PromptLibraryEntry>) {
    setDraft(prev => prev ? { ...prev, ...patch } : prev)
  }

  // ── render ──────────────────────────────────────────────────────────────────

  return (
    <div className="fixed inset-0 z-50 bg-black/75 flex items-center justify-center p-6">
      <div className="w-full max-w-5xl max-h-[88vh] bg-gray-950 border border-gray-700 rounded-xl overflow-hidden flex flex-col">

        {/* Header */}
        <div className="px-5 py-3 border-b border-gray-800 flex items-center justify-between flex-shrink-0">
          <div className="flex items-center gap-2">
            <BookOpen className="w-4 h-4 text-gray-400" />
            <span className="text-sm font-semibold text-gray-100">Prompt Library</span>
          </div>
          <button onClick={onClose} className="text-gray-500 hover:text-gray-200 transition-colors">
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 min-h-0 flex overflow-hidden">

          {/* Left — entry list */}
          <div className="w-64 flex-shrink-0 border-r border-gray-800 flex flex-col">
            <div className="px-3 py-2 border-b border-gray-800 flex-shrink-0">
              <button
                onClick={handleNew}
                className="w-full flex items-center justify-center gap-1.5 px-2 py-1.5 rounded bg-emerald-700 hover:bg-emerald-600 text-white text-xs"
              >
                <Plus className="w-3.5 h-3.5" />
                New Entry
              </button>
            </div>

            <div className="flex-1 overflow-y-auto">
              {loading && (
                <p className="px-3 py-3 text-xs text-gray-500 animate-pulse">Loading…</p>
              )}
              {!loading && entries.length === 0 && (
                <p className="px-3 py-3 text-xs text-gray-500">No entries yet. Click "New Entry" to start.</p>
              )}
              {sortedEntries(entries).map(entry => (
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
                </button>
              ))}
            </div>
          </div>

          {/* Right — editor */}
          <div className="flex-1 overflow-y-auto p-4 space-y-3">
            {!draft && (
              <p className="text-xs text-gray-500 mt-6 text-center">Select an entry from the list or create a new one.</p>
            )}

            {draft && (
              <>
                {/* Row: Name + Version + actions */}
                <div className="flex items-end gap-2">
                  <label className="flex-1 text-xs text-gray-400">
                    Name
                    <input
                      value={draft.name}
                      onChange={e => patchDraft({ name: e.target.value })}
                      className="mt-0.5 w-full bg-gray-800 border border-gray-600 rounded px-2 py-1 text-sm text-gray-200"
                      placeholder="E.g. Scalping Analyst"
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

                {/* Description — multiline */}
                <label className="block text-xs text-gray-400">
                  Description
                  <textarea
                    rows={3}
                    value={draft.description}
                    onChange={e => patchDraft({ description: e.target.value })}
                    className="mt-0.5 w-full bg-gray-800 border border-gray-600 rounded px-2 py-1 text-sm text-gray-200 resize-y"
                    placeholder="What does this prompt do?"
                  />
                </label>

                {/* Prompt text */}
                <div>
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-xs text-gray-400">Prompt</span>
                    <div className="flex items-center gap-1.5">
                      <CopyButton getText={() => draft.text} />
                      <button
                        type="button"
                        title="Open in full-screen editor"
                        onClick={() => setPromptExpanded(true)}
                        className="inline-flex items-center text-gray-500 hover:text-gray-300 transition-colors"
                      >
                        <Maximize2 className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  </div>
                  <textarea
                    key={draft.id}
                    rows={14}
                    value={draft.text}
                    onChange={e => patchDraft({ text: e.target.value })}
                    className="w-full bg-gray-800 border border-gray-600 rounded px-2 py-1.5 text-sm text-gray-200 font-mono resize-y focus:outline-none focus:border-gray-500"
                    spellCheck={false}
                    placeholder="Enter the prompt text…"
                  />
                </div>
              </>
            )}

            {/* Status messages */}
            {message && <p className="text-xs text-emerald-400">{message}</p>}
            {error   && <p className="text-xs text-red-400">{error}</p>}
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
          <div className="flex items-center gap-2">
            <span className="text-xs text-gray-500 mr-1">Apply to prompt:</span>
            <button
              onClick={() => { if (draft?.text) { onInsert(draft.text); onClose() } }}
              disabled={!draft?.text}
              title="Append this prompt to the existing prompt text"
              className="px-3 py-1.5 rounded border border-blue-700 bg-blue-900/40 text-blue-300 hover:bg-blue-800/60 text-sm disabled:opacity-40 disabled:cursor-not-allowed"
            >
              Append
            </button>
            <button
              onClick={() => { if (draft?.text) { onReplace(draft.text); onClose() } }}
              disabled={!draft?.text}
              title="Replace the existing prompt text with this one"
              className="px-3 py-1.5 rounded border border-amber-700 bg-amber-900/40 text-amber-300 hover:bg-amber-800/60 text-sm disabled:opacity-40 disabled:cursor-not-allowed"
            >
              Replace
            </button>
          </div>
        </div>

      </div>

      {/* Prompt expand modal */}
      {promptExpanded && draft && (
        <div className="fixed inset-0 z-60 bg-black/80 flex items-center justify-center p-6">
          <div className="w-full max-w-4xl max-h-[90vh] bg-gray-950 border border-gray-700 rounded-xl overflow-hidden flex flex-col">
            <div className="px-5 py-3 border-b border-gray-800 flex items-center justify-between flex-shrink-0">
              <span className="text-sm font-semibold text-gray-100">
                {draft.name ? `${draft.name} · v${draft.version}` : 'Prompt Text'}
              </span>
              <div className="flex items-center gap-2">
                <CopyButton getText={() => draft.text} />
                <button
                  onClick={() => setPromptExpanded(false)}
                  className="px-3 py-1 rounded border border-gray-700 bg-gray-900 text-gray-300 hover:text-white text-sm"
                >
                  Close
                </button>
              </div>
            </div>
            <div className="flex-1 overflow-auto p-5">
              <textarea
                rows={30}
                value={draft.text}
                onChange={e => patchDraft({ text: e.target.value })}
                className="w-full h-full bg-gray-900 border border-gray-700 rounded px-3 py-2 text-sm text-gray-200 font-mono leading-6 resize-none focus:outline-none focus:border-gray-500"
                spellCheck={false}
              />
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
