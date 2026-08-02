/**
 * JsonViewer — collapsible JSON tree with in-tree search + highlight.
 *
 * Wraps react-json-view-lite's <JsonView> (which already gives per-node
 * expand/collapse for free) with a search box that:
 *  - auto-expands every branch containing a match (via shouldExpandNode,
 *    which is handed the node's own subtree as `value` — no path tracking
 *    needed), and
 *  - highlights matched text with <mark>, via a small DOM pass after render
 *    (react-json-view-lite has no render-prop hook for value/key text, so
 *    this is the only way to inject highlighting without forking it).
 *
 * Used anywhere the Prompt/Simulation Workbench shows a raw JSON blob
 * (decision, script input/result, snapshot, last EC input, context preview)
 * so users can search instead of eyeballing a huge flat dump.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Search, X } from 'lucide-react'
import { JsonView, darkStyles } from 'react-json-view-lite'
import 'react-json-view-lite/dist/index.css'

interface JsonViewerProps {
  data: unknown
  /** Levels below this are expanded by default when there is no active search. Default 1 (top-level keys visible). */
  defaultExpandLevel?: number
  emptyText?: string
  className?: string
}

function containsMatch(value: unknown, query: string): boolean {
  if (value == null) return false
  if (typeof value === 'string') return value.toLowerCase().includes(query)
  if (typeof value === 'number' || typeof value === 'boolean') return String(value).toLowerCase().includes(query)
  if (Array.isArray(value)) return value.some(v => containsMatch(v, query))
  if (typeof value === 'object') {
    return Object.entries(value as Record<string, unknown>).some(
      ([key, v]) => key.toLowerCase().includes(query) || containsMatch(v, query),
    )
  }
  return false
}

const MARK_ATTR = 'data-json-search-mark'

function clearHighlights(root: HTMLElement): void {
  const marks = root.querySelectorAll(`mark[${MARK_ATTR}]`)
  marks.forEach(mark => {
    const parent = mark.parentNode
    if (!parent) return
    parent.replaceChild(document.createTextNode(mark.textContent ?? ''), mark)
    parent.normalize()
  })
}

function applyHighlights(root: HTMLElement, query: string): number {
  if (!query) return 0
  const lowerQuery = query.toLowerCase()
  let count = 0
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT)
  const textNodes: Text[] = []
  let node: Node | null = walker.nextNode()
  while (node) {
    textNodes.push(node as Text)
    node = walker.nextNode()
  }
  for (const textNode of textNodes) {
    const text = textNode.textContent ?? ''
    const lower = text.toLowerCase()
    if (!lower.includes(lowerQuery)) continue
    const frag = document.createDocumentFragment()
    let idx = 0
    let pos = lower.indexOf(lowerQuery)
    while (pos !== -1) {
      if (pos > idx) frag.appendChild(document.createTextNode(text.slice(idx, pos)))
      const mark = document.createElement('mark')
      mark.setAttribute(MARK_ATTR, '1')
      mark.className = 'bg-yellow-400/90 text-black rounded-sm'
      mark.textContent = text.slice(pos, pos + query.length)
      frag.appendChild(mark)
      count += 1
      idx = pos + query.length
      pos = lower.indexOf(lowerQuery, idx)
    }
    if (idx < text.length) frag.appendChild(document.createTextNode(text.slice(idx)))
    textNode.parentNode?.replaceChild(frag, textNode)
  }
  return count
}

export function JsonViewer({ data, defaultExpandLevel = 1, emptyText = '(leer)', className }: JsonViewerProps) {
  const [query, setQuery] = useState('')
  const [debouncedQuery, setDebouncedQuery] = useState('')
  const [matchCount, setMatchCount] = useState(0)
  const containerRef = useRef<HTMLDivElement | null>(null)

  // Debounced so typing doesn't re-walk/re-expand a large tree on every keystroke.
  useEffect(() => {
    const t = setTimeout(() => setDebouncedQuery(query.trim().toLowerCase()), 200)
    return () => clearTimeout(t)
  }, [query])

  const shouldExpandNode = useCallback(
    (level: number, value: unknown) =>
      level < defaultExpandLevel || (debouncedQuery !== '' && containsMatch(value, debouncedQuery)),
    [debouncedQuery, defaultExpandLevel],
  )

  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    // One frame so react-json-view-lite's own expand-state effect (triggered by the new
    // shouldExpandNode identity above) has committed its DOM changes before we scan it.
    const raf = requestAnimationFrame(() => {
      clearHighlights(el)
      const count = debouncedQuery ? applyHighlights(el, debouncedQuery) : 0
      setMatchCount(count)
      if (count > 0) {
        el.querySelector(`mark[${MARK_ATTR}]`)?.scrollIntoView({ block: 'nearest' })
      }
    })
    return () => cancelAnimationFrame(raf)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debouncedQuery, data, shouldExpandNode])

  const isEmpty = useMemo(() => {
    if (data == null) return true
    if (Array.isArray(data)) return data.length === 0
    if (typeof data === 'object') return Object.keys(data as object).length === 0
    return false
  }, [data])

  return (
    <div className={className}>
      <div className="flex items-center gap-1.5 mb-1">
        <Search className="w-3 h-3 text-gray-500 flex-shrink-0" />
        <input
          value={query}
          onChange={e => setQuery(e.target.value)}
          placeholder="In JSON suchen…"
          className="flex-1 min-w-0 bg-gray-950 border border-gray-700 rounded px-1.5 py-0.5 text-[11px] text-gray-200 focus:outline-none focus:border-emerald-500"
        />
        {query && (
          <>
            <span className="text-[10px] text-gray-500 whitespace-nowrap">
              {debouncedQuery ? `${matchCount} Treffer` : '…'}
            </span>
            <button
              type="button"
              onClick={() => setQuery('')}
              className="text-gray-500 hover:text-gray-300 flex-shrink-0"
              title="Suche löschen"
            >
              <X className="w-3 h-3" />
            </button>
          </>
        )}
      </div>
      <div ref={containerRef} className="overflow-x-auto">
        {isEmpty ? (
          <span className="text-gray-600 italic text-[11px]">{emptyText}</span>
        ) : (
          <JsonView data={data as object} style={darkStyles} shouldExpandNode={shouldExpandNode} />
        )}
      </div>
    </div>
  )
}
