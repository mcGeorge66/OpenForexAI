import { useState } from 'react'
import type { KbDocMeta } from '@/api/client'
import { ChevronRight, ChevronDown, Folder, FolderOpen, FileText, MoreHorizontal, Plus, Trash2, Edit3, FolderPlus, FolderInput, X } from 'lucide-react'

interface Props {
  docs: KbDocMeta[]
  activeId: string | null
  onSelect: (id: string) => void
  onCreate: (parentId: string | null, isFolder: boolean) => void
  onDelete: (id: string) => void
  onRename: (id: string, title: string) => void
  onMove: (id: string, newParentId: string | null) => void
}

function MovePicker({ doc, docs, onMove, onClose }: {
  doc: KbDocMeta
  docs: KbDocMeta[]
  onMove: (newParentId: string | null) => void
  onClose: () => void
}) {
  const folders = docs.filter(d => d.is_folder && d.id !== doc.id)
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={onClose}>
      <div className="bg-gray-900 border border-gray-700 rounded-lg shadow-2xl w-72 p-4"
        onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-3">
          <span className="text-sm font-semibold text-gray-200">Verschieben nach…</span>
          <button onClick={onClose} className="text-gray-500 hover:text-gray-300"><X className="w-4 h-4" /></button>
        </div>
        <div className="space-y-1 max-h-60 overflow-y-auto">
          <button
            onClick={() => onMove(null)}
            className="w-full text-left flex items-center gap-2 px-3 py-2 rounded text-sm text-gray-300 hover:bg-gray-800 transition-colors"
          >
            <Folder className="w-3.5 h-3.5 text-gray-500" /> Root (kein Ordner)
          </button>
          {folders.map(f => (
            <button
              key={f.id}
              onClick={() => onMove(f.id)}
              disabled={doc.parent_id === f.id}
              className="w-full text-left flex items-center gap-2 px-3 py-2 rounded text-sm text-gray-300 hover:bg-gray-800 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
            >
              <Folder className="w-3.5 h-3.5 text-amber-400" /> {f.title}
            </button>
          ))}
          {folders.length === 0 && (
            <p className="px-3 py-2 text-xs text-gray-600">Keine Ordner vorhanden</p>
          )}
        </div>
      </div>
    </div>
  )
}

function buildTree(docs: KbDocMeta[]): Map<string | null, KbDocMeta[]> {
  const map = new Map<string | null, KbDocMeta[]>()
  for (const doc of docs) {
    const key = doc.parent_id ?? null
    if (!map.has(key)) map.set(key, [])
    map.get(key)!.push(doc)
  }
  return map
}

function TreeNode({
  doc, tree, docs, activeId, depth,
  onSelect, onCreate, onDelete, onRename, onMove,
}: {
  doc: KbDocMeta
  tree: Map<string | null, KbDocMeta[]>
  docs: KbDocMeta[]
  activeId: string | null
  depth: number
  onSelect: (id: string) => void
  onCreate: (parentId: string | null, isFolder: boolean) => void
  onDelete: (id: string) => void
  onRename: (id: string, title: string) => void
  onMove: (id: string, newParentId: string | null) => void
}) {
  const [open, setOpen] = useState(true)
  const [menuOpen, setMenuOpen] = useState(false)
  const [renaming, setRenaming] = useState(false)
  const [renameVal, setRenameVal] = useState(doc.title)
  const [moveOpen, setMoveOpen] = useState(false)
  const children = tree.get(doc.id) ?? []
  const isFolder = !!doc.is_folder
  const isActive = doc.id === activeId

  const handleRename = () => {
    if (renameVal.trim() && renameVal !== doc.title) {
      onRename(doc.id, renameVal.trim())
    }
    setRenaming(false)
  }

  return (
    <div>
      <div
        className={[
          'group flex items-center gap-1 px-2 py-1 cursor-pointer text-sm transition-colors',
          isActive ? 'bg-emerald-900/40 text-emerald-300' : 'text-gray-400 hover:text-gray-200 hover:bg-gray-800',
        ].join(' ')}
        style={{ paddingLeft: `${8 + depth * 14}px` }}
        onClick={() => isFolder ? setOpen(o => !o) : onSelect(doc.id)}
      >
        {isFolder ? (
          <span className="flex-shrink-0 w-3.5 h-3.5 text-gray-500">
            {open ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
          </span>
        ) : (
          <span className="w-3.5 h-3.5 flex-shrink-0" />
        )}
        {isFolder
          ? open ? <FolderOpen className="w-3.5 h-3.5 text-amber-400 flex-shrink-0" />
                  : <Folder className="w-3.5 h-3.5 text-amber-400 flex-shrink-0" />
          : <FileText className="w-3.5 h-3.5 flex-shrink-0 text-gray-500" />
        }
        {renaming ? (
          <input
            autoFocus
            value={renameVal}
            onChange={e => setRenameVal(e.target.value)}
            onBlur={handleRename}
            onKeyDown={e => { if (e.key === 'Enter') handleRename(); if (e.key === 'Escape') setRenaming(false) }}
            onClick={e => e.stopPropagation()}
            className="flex-1 bg-gray-800 border border-gray-600 rounded px-1 text-xs text-gray-200 outline-none"
          />
        ) : (
          <span className="flex-1 truncate text-xs">{doc.title}</span>
        )}
        <button
          className="opacity-0 group-hover:opacity-100 flex-shrink-0 p-0.5 rounded hover:bg-gray-700 transition-opacity"
          onClick={e => { e.stopPropagation(); setMenuOpen(o => !o) }}
        >
          <MoreHorizontal className="w-3 h-3" />
        </button>
      </div>

      {menuOpen && (
        <div
          className="fixed z-50 bg-gray-800 border border-gray-600 rounded shadow-xl py-1 text-xs"
          style={{ marginLeft: `${40 + depth * 14}px` }}
          onMouseLeave={() => setMenuOpen(false)}
        >
          <button className="flex items-center gap-2 w-full px-3 py-1.5 hover:bg-gray-700 text-gray-300"
            onClick={() => { setRenaming(true); setMenuOpen(false) }}>
            <Edit3 className="w-3 h-3" /> Umbenennen
          </button>
          {isFolder && (
            <>
              <button className="flex items-center gap-2 w-full px-3 py-1.5 hover:bg-gray-700 text-gray-300"
                onClick={() => { onCreate(doc.id, false); setMenuOpen(false) }}>
                <Plus className="w-3 h-3" /> Dokument hier
              </button>
              <button className="flex items-center gap-2 w-full px-3 py-1.5 hover:bg-gray-700 text-gray-300"
                onClick={() => { onCreate(doc.id, true); setMenuOpen(false) }}>
                <FolderPlus className="w-3 h-3" /> Ordner hier
              </button>
            </>
          )}
          <div className="border-t border-gray-700 my-1" />
          <button className="flex items-center gap-2 w-full px-3 py-1.5 hover:bg-gray-700 text-gray-300"
            onClick={() => { setMoveOpen(true); setMenuOpen(false) }}>
            <FolderInput className="w-3 h-3" /> Verschieben
          </button>
          <div className="border-t border-gray-700 my-1" />
          <button className="flex items-center gap-2 w-full px-3 py-1.5 hover:bg-gray-700 text-red-400"
            onClick={() => { onDelete(doc.id); setMenuOpen(false) }}>
            <Trash2 className="w-3 h-3" /> Löschen
          </button>
        </div>
      )}

      {moveOpen && (
        <MovePicker
          doc={doc}
          docs={docs}
          onMove={newParentId => { onMove(doc.id, newParentId); setMoveOpen(false) }}
          onClose={() => setMoveOpen(false)}
        />
      )}

      {isFolder && open && children.map(child => (
        <TreeNode
          key={child.id}
          doc={child}
          tree={tree}
          docs={docs}
          activeId={activeId}
          depth={depth + 1}
          onSelect={onSelect}
          onCreate={onCreate}
          onDelete={onDelete}
          onRename={onRename}
          onMove={onMove}
        />
      ))}
    </div>
  )
}

export function DocTree({ docs, activeId, onSelect, onCreate, onDelete, onRename, onMove }: Props) {
  const tree = buildTree(docs)
  const roots = tree.get(null) ?? []

  return (
    <div className="py-2">
      {roots.length === 0 && (
        <p className="px-4 py-2 text-xs text-gray-600">Keine Dokumente</p>
      )}
      {roots.map(doc => (
        <TreeNode
          key={doc.id}
          doc={doc}
          tree={tree}
          docs={docs}
          activeId={activeId}
          depth={0}
          onSelect={onSelect}
          onCreate={onCreate}
          onDelete={onDelete}
          onRename={onRename}
          onMove={onMove}
        />
      ))}
    </div>
  )
}
