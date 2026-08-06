/**
 * Shared types, parser, and patch engine for LLM assistant panels.
 * Used by EntityAssistantPanel, PromptAssistantPanel, ScriptAssistantPanel, and
 * MessageBubble.tsx (split into its own file so this one stays component-free —
 * a Fast Refresh requirement).
 */

import type React from 'react'
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
