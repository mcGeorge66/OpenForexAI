import { useEffect, useRef } from 'react'
import type { KbSearchResult } from '@/api/client'
import { Search, X, FileText } from 'lucide-react'

interface Props {
  query: string
  results: KbSearchResult[]
  onQuery: (q: string) => void
  onNavigate: (id: string) => void
  onClose: () => void
}

export function SearchPanel({ query, results, onQuery, onNavigate, onClose }: Props) {
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    inputRef.current?.focus()
  }, [])

  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onClose])

  return (
    <div className="absolute inset-0 z-50 bg-black/60 flex items-start justify-center pt-16 px-4 print:hidden">
      <div className="w-full max-w-xl bg-gray-900 border border-gray-700 rounded-lg shadow-2xl overflow-hidden">
        <div className="flex items-center gap-2 px-4 py-3 border-b border-gray-700">
          <Search className="w-4 h-4 text-gray-400 flex-shrink-0" />
          <input
            ref={inputRef}
            value={query}
            onChange={e => onQuery(e.target.value)}
            placeholder="Dokumentübergreifend suchen…"
            className="flex-1 bg-transparent text-sm text-gray-200 outline-none placeholder-gray-600"
          />
          <button onClick={onClose} className="text-gray-500 hover:text-gray-300 transition-colors">
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="max-h-96 overflow-y-auto">
          {query && results.length === 0 && (
            <p className="px-4 py-6 text-sm text-gray-600 text-center">Keine Treffer</p>
          )}
          {results.map(r => (
            <button
              key={r.doc_id}
              onClick={() => onNavigate(r.doc_id)}
              className="w-full text-left px-4 py-3 hover:bg-gray-800 transition-colors border-b border-gray-800 last:border-0"
            >
              <div className="flex items-center gap-2 mb-1">
                <FileText className="w-3.5 h-3.5 text-gray-500 flex-shrink-0" />
                <span className="text-sm text-gray-200 font-medium">{r.title}</span>
              </div>
              {r.snippet && (
                <p
                  className="text-xs text-gray-500 line-clamp-2 pl-5 [&_mark]:bg-emerald-900/60 [&_mark]:text-emerald-300 [&_mark]:rounded"
                  dangerouslySetInnerHTML={{ __html: r.snippet }}
                />
              )}
            </button>
          ))}
          {!query && (
            <p className="px-4 py-6 text-sm text-gray-600 text-center">Suchbegriff eingeben…</p>
          )}
        </div>
      </div>
    </div>
  )
}
