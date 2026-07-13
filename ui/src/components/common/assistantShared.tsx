/**
 * Shared types, parser, patch engine, and MessageBubble for LLM assistant panels.
 * Used by EntityAssistantPanel and ScriptAssistantPanel.
 */

import React, { useState } from 'react'
import { Check, Copy, Pencil, FlaskConical, AlertTriangle } from 'lucide-react'
import type { LLMAssistantMessage } from '@/api/client'

// ─── Types ────────────────────────────────────────────────────────────────────

export type FullBlock = {
  kind: 'full'
  target: 'script' | 'config' | 'other'
  lang: string
  code: string
}

export type PatchBlock = {
  kind: 'patch'
  target: 'script' | 'config'
  startLine: number  // 1-based
  endLine: number    // 1-based, inclusive
  code: string
  insert: boolean    // true = INSERT AFTER, false = REPLACE
}

export type Segment =
  | { type: 'text'; content: string }
  | { type: 'full'; block: FullBlock }
  | { type: 'patch'; block: PatchBlock }

export interface ParsedResponse {
  segments: Segment[]
  triggerRun: boolean
}

export type AssistantMessage = LLMAssistantMessage & { parsed?: ParsedResponse }

// ─── Patch engine ─────────────────────────────────────────────────────────────

export function applyPatch(source: string, patch: PatchBlock): { result: string; error?: string } {
  const lines = source.split('\n')
  const total = lines.length
  const { startLine, endLine, code, insert } = patch

  if (insert) {
    if (startLine < 0 || startLine > total) {
      return { result: source, error: `INSERT AFTER L${startLine}: Zeile existiert nicht (${total} Zeilen)` }
    }
    const newLines = code.endsWith('\n') ? code.slice(0, -1).split('\n') : code.split('\n')
    return { result: [...lines.slice(0, startLine), ...newLines, ...lines.slice(startLine)].join('\n') }
  }

  if (startLine < 1 || endLine > total || startLine > endLine) {
    return { result: source, error: `PATCH L${startLine}-L${endLine}: Zeilenbereich ungültig (${total} Zeilen)` }
  }
  const newLines = code.endsWith('\n') ? code.slice(0, -1).split('\n') : code.split('\n')
  return { result: [...lines.slice(0, startLine - 1), ...newLines, ...lines.slice(endLine)].join('\n') }
}

// ─── Response parser ──────────────────────────────────────────────────────────

export function parseResponse(text: string): ParsedResponse {
  const triggerRun = text.includes('<<RUN_TEST>>')
  const work = text.replace(/<<RUN_TEST>>/g, '').trimEnd()

  const segments: Segment[] = []
  const RE = /<<<(PATCH|INSERT)\s+(SCRIPT|CONFIG)(?:\s+(?:AFTER\s+)?L(\d+)(?:-L?(\d+))?)?>>>([\s\S]*?)<<<END>>>|```([\w]*)\n([\s\S]*?)```/g

  let lastIndex = 0
  let m: RegExpExecArray | null

  while ((m = RE.exec(work)) !== null) {
    const before = work.slice(lastIndex, m.index)
    if (before.trim()) segments.push({ type: 'text', content: before })
    lastIndex = m.index + m[0].length

    if (m[1]) {
      const op = m[1]
      const tgt = m[2]
      const l1 = m[3] ? parseInt(m[3], 10) : null
      const l2 = m[4] ? parseInt(m[4], 10) : null
      const code = (m[5] ?? '').replace(/^\n/, '')
      const target = tgt === 'CONFIG' ? 'config' : 'script'
      const insert = op === 'INSERT'

      if (l1 !== null) {
        segments.push({
          type: 'patch',
          block: { kind: 'patch', target, startLine: l1, endLine: insert ? l1 : (l2 ?? l1), code, insert },
        })
      } else {
        segments.push({ type: 'text', content: '[Patch ohne Zeilenangabe ignoriert]' })
      }
    } else {
      const rawLang = (m[6] ?? '').toLowerCase()
      const code = m[7] ?? ''
      const target: FullBlock['target'] =
        rawLang === 'python' ? 'script' : rawLang === 'json' ? 'config' : 'other'
      segments.push({ type: 'full', block: { kind: 'full', target, lang: rawLang || 'text', code } })
    }
  }

  const tail = work.slice(lastIndex)
  if (tail.trim()) segments.push({ type: 'text', content: tail })

  return { segments, triggerRun }
}

// ─── Inline text renderer ─────────────────────────────────────────────────────

export function renderInlineText(text: string): React.ReactNode {
  const parts = text.split(/(`[^`]+`)/g)
  if (parts.length === 1) return <span>{text}</span>
  return (
    <>
      {parts.map((s, i) => {
        const m = s.match(/^`([^`]+)`$/)
        if (m)
          return <code key={i} className="rounded bg-gray-900 border border-gray-700 px-1 font-mono text-emerald-300 text-[11px]">{m[1]}</code>
        return <span key={i}>{s}</span>
      })}
    </>
  )
}

// ─── MessageBubble ────────────────────────────────────────────────────────────

export interface MessageBubbleProps {
  msg: AssistantMessage
  autoWrite: boolean
  currentScript: string
  currentConfig?: string
  onApplyScript: (code: string) => void
  onApplyConfig?: (json: string) => void
}

export function MessageBubble({ msg, autoWrite, currentScript, currentConfig = '{}', onApplyScript, onApplyConfig }: MessageBubbleProps) {
  const [applied, setApplied] = useState<Record<number, boolean>>({})
  const [copied, setCopied] = useState<Record<number, boolean>>({})
  const [patchErrors, setPatchErrors] = useState<Record<number, string>>({})

  if (msg.role === 'user') {
    return (
      <div className="flex justify-end">
        <div className="max-w-[80%] rounded-lg px-3 py-1.5 text-xs bg-blue-900/60 text-blue-100 whitespace-pre-wrap">
          {msg.content}
        </div>
      </div>
    )
  }

  const parsed = msg.parsed ?? parseResponse(msg.content)

  const markCopied = (i: number) => {
    setCopied(s => ({ ...s, [i]: true }))
    setTimeout(() => setCopied(s => ({ ...s, [i]: false })), 1500)
  }
  const markApplied = (i: number) => {
    setApplied(s => ({ ...s, [i]: true }))
    setTimeout(() => setApplied(s => ({ ...s, [i]: false })), 1500)
  }

  return (
    <div className="flex justify-start">
      <div className="max-w-[95%] space-y-1.5">
        {parsed.segments.map((seg, i) => {
          if (seg.type === 'text') {
            return (
              <div key={i} className="rounded-lg px-3 py-1.5 text-xs bg-gray-800 text-gray-200 whitespace-pre-wrap">
                {renderInlineText(seg.content)}
              </div>
            )
          }

          if (seg.type === 'full') {
            const { block } = seg
            const canApply = block.target === 'script' || (block.target === 'config' && !!onApplyConfig)
            const label = block.target === 'script' ? 'Script ersetzen' : block.target === 'config' ? 'Config ersetzen' : null

            return (
              <div key={i} className="rounded border border-gray-700 overflow-hidden">
                <div className="flex items-center justify-between px-2 py-1 bg-gray-900 border-b border-gray-700">
                  <span className="text-[10px] font-mono text-gray-500">{block.lang} · vollständig</span>
                  <div className="flex items-center gap-2">
                    <button type="button" onClick={() => { void navigator.clipboard.writeText(block.code).then(() => markCopied(i)) }}
                      className="flex items-center gap-1 text-[10px] text-gray-500 hover:text-gray-300 transition-colors">
                      {copied[i] ? <><Check className="w-3 h-3 text-emerald-400" /><span className="text-emerald-400">Copied</span></> : <><Copy className="w-3 h-3" />Copy</>}
                    </button>
                    {canApply && !autoWrite && label && (
                      <button type="button" onClick={() => {
                        if (block.target === 'script') onApplyScript(block.code)
                        if (block.target === 'config') onApplyConfig?.(block.code)
                        markApplied(i)
                      }} className="flex items-center gap-1 text-[10px] text-emerald-400 hover:text-emerald-300 border border-emerald-700 rounded px-1.5 py-0.5 transition-colors">
                        {applied[i] ? <><Check className="w-3 h-3" />Applied</> : <><Pencil className="w-3 h-3" />{label}</>}
                      </button>
                    )}
                    {canApply && autoWrite && <span className="text-[10px] text-emerald-500 italic">auto-applied</span>}
                  </div>
                </div>
                <pre className="px-3 py-2 text-[11px] font-mono text-emerald-300 overflow-x-auto whitespace-pre bg-gray-950">{block.code}</pre>
              </div>
            )
          }

          if (seg.type === 'patch') {
            const { block } = seg
            const rangeLabel = block.insert
              ? `INSERT AFTER L${block.startLine}`
              : block.startLine === block.endLine ? `L${block.startLine}` : `L${block.startLine}–L${block.endLine}`
            const targetLabel = block.target === 'script' ? 'Script' : 'Config'
            const canApply = block.target === 'script' || (block.target === 'config' && !!onApplyConfig)

            return (
              <div key={i} className="rounded border border-indigo-800/60 overflow-hidden">
                <div className="flex items-center justify-between px-2 py-1 bg-gray-900 border-b border-indigo-800/40">
                  <span className="text-[10px] font-mono text-indigo-400">patch {targetLabel} · {rangeLabel}</span>
                  <div className="flex items-center gap-2">
                    <button type="button" onClick={() => { void navigator.clipboard.writeText(block.code).then(() => markCopied(i)) }}
                      className="flex items-center gap-1 text-[10px] text-gray-500 hover:text-gray-300 transition-colors">
                      {copied[i] ? <><Check className="w-3 h-3 text-emerald-400" /><span className="text-emerald-400">Copied</span></> : <><Copy className="w-3 h-3" />Copy</>}
                    </button>
                    {canApply && !autoWrite && (
                      <button type="button" onClick={() => {
                        const source = block.target === 'script' ? currentScript : currentConfig
                        const { result, error } = applyPatch(source, block)
                        if (error) { setPatchErrors(s => ({ ...s, [i]: error })); return }
                        if (block.target === 'script') onApplyScript(result)
                        if (block.target === 'config') onApplyConfig?.(result)
                        markApplied(i)
                        setPatchErrors(s => { const n = { ...s }; delete n[i]; return n })
                      }} className="flex items-center gap-1 text-[10px] text-indigo-400 hover:text-indigo-300 border border-indigo-700 rounded px-1.5 py-0.5 transition-colors">
                        {applied[i] ? <><Check className="w-3 h-3" />Applied</> : <><Pencil className="w-3 h-3" />Apply patch</>}
                      </button>
                    )}
                    {canApply && autoWrite && <span className="text-[10px] text-indigo-400 italic">auto-applied</span>}
                  </div>
                </div>
                <pre className="px-3 py-2 text-[11px] font-mono text-indigo-300 overflow-x-auto whitespace-pre bg-gray-950">{block.code}</pre>
                {patchErrors[i] && (
                  <div className="flex items-center gap-1.5 px-2 py-1 text-[10px] text-red-400 bg-red-900/20 border-t border-red-800/40">
                    <AlertTriangle className="w-3 h-3 flex-shrink-0" />{patchErrors[i]}
                  </div>
                )}
              </div>
            )
          }

          return null
        })}

        {parsed.triggerRun && (
          <div className="flex items-center gap-1.5 px-2 py-1 text-[10px] text-amber-400 bg-amber-900/20 border border-amber-800/40 rounded">
            <FlaskConical className="w-3 h-3" />
            Test wurde ausgelöst…
          </div>
        )}
      </div>
    </div>
  )
}
