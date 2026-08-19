/**
 * Shared types, parser, and patch engine for LLM assistant panels.
 * Used by EntityAssistantPanel, PromptAssistantPanel, ScriptAssistantPanel, and
 * MessageBubble.tsx (split into its own file so this one stays component-free —
 * a Fast Refresh requirement).
 */

import type React from 'react'
import type { LLMAssistantMessage, LLMAssistantProposal } from '@/api/client'

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

// A hunk from a standard unified diff (```diff fence with ---/+++/@@ markers) —
// models fall back to this well-known format instead of the app's <<<PATCH>>>
// syntax often enough that it needs first-class support, not just detection.
// Unlike PatchBlock, this has no line numbers (real responses often omit the
// @@ -a,b +c,d @@ counts entirely) — it's located and applied by exact text
// match instead, which is also more forgiving of the model miscounting lines.
export type DiffHunkBlock = {
  kind: 'diffhunk'
  target: 'script' | 'config'
  searchText: string   // old lines (context + removed), joined by \n
  replaceText: string  // new lines (context + added), joined by \n
}

export type Segment =
  | { type: 'text'; content: string }
  | { type: 'full'; block: FullBlock }
  | { type: 'patch'; block: PatchBlock }
  | { type: 'diffhunk'; block: DiffHunkBlock }

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

// Apply a unified-diff hunk by exact text search rather than line numbers — the
// hunk's "old" lines must appear verbatim, exactly once, in `source`. Errors out
// (never silently guesses) if the anchor text is missing or ambiguous, since a
// wrong-location replace would corrupt the script/config in a way that's hard to notice.
export function applyDiffHunk(source: string, hunk: DiffHunkBlock): { result: string; error?: string } {
  const { searchText, replaceText } = hunk
  if (!searchText.trim()) {
    return { result: source, error: 'Diff hunk has no unchanged/removed context to locate — cannot apply safely.' }
  }
  const idx = source.indexOf(searchText)
  if (idx === -1) {
    return { result: source, error: 'Could not find the exact lines this diff expects to change — the file may have changed since the assistant last read it.' }
  }
  if (source.indexOf(searchText, idx + 1) !== -1) {
    return { result: source, error: 'The lines this diff targets appear more than once in the file — cannot apply unambiguously.' }
  }
  return { result: source.slice(0, idx) + replaceText + source.slice(idx + searchText.length) }
}

// Parse a ```diff fenced block's body into one or more DiffHunkBlocks. Splits on
// "+++ <file>" to pick the target (script vs config) and on "@@" hunk separators
// (their -a,b/+c,d counts are ignored/untrusted — often missing in practice).
function parseUnifiedDiff(diffText: string, defaultTarget: 'script' | 'config'): DiffHunkBlock[] {
  const lines = diffText.split('\n')
  const blocks: DiffHunkBlock[] = []
  let target: 'script' | 'config' = defaultTarget
  let searchLines: string[] = []
  let replaceLines: string[] = []

  const flush = () => {
    if (searchLines.length || replaceLines.length) {
      blocks.push({
        kind: 'diffhunk',
        target,
        searchText: searchLines.join('\n'),
        replaceText: replaceLines.join('\n'),
      })
    }
    searchLines = []
    replaceLines = []
  }

  for (const line of lines) {
    if (/^---\s/.test(line)) { flush(); continue }
    const plusMatch = /^\+\+\+\s+(.+)$/.exec(line)
    if (plusMatch) {
      flush()
      target = /config|\.json\b/i.test(plusMatch[1]) ? 'config' : 'script'
      continue
    }
    if (/^@@/.test(line)) { flush(); continue }
    if (line.startsWith('-')) { searchLines.push(line.slice(1)); continue }
    if (line.startsWith('+')) { replaceLines.push(line.slice(1)); continue }
    if (line.startsWith(' ')) { searchLines.push(line.slice(1)); replaceLines.push(line.slice(1)); continue }
    // blank separator line between hunks/files — not a blank context line
    // (a real blank context line is written as a single space per the diff format)
  }
  flush()
  return blocks
}

// ─── Response parser ──────────────────────────────────────────────────────────

// Models occasionally wrap their ENTIRE reply — explanation, headings, nested code
// snippets, everything — in one big outer ``` fence (worse case of the same habit
// that motivates the patch-fence unwrap below). Legitimate Option-B full-replace
// blocks always use `python`/`json` as the language tag, so those are left alone;
// anything else is only unwrapped if the inside clearly looks like a whole rich
// answer (nested fences, patch markers, or markdown headings) rather than one
// literal file's content, to avoid false positives on a genuine plain-text sample.
function unwrapAccidentalOuterFence(text: string): string {
  const trimmed = text.trim()
  const m = /^```([\w]*)\n([\s\S]*)\n```$/.exec(trimmed)
  if (!m) return text
  const lang = m[1].toLowerCase()
  if (lang === 'python' || lang === 'json') return text
  const inner = m[2]
  const looksLikeWholeAnswer = /```/.test(inner) || /<<<(PATCH|INSERT)\b/.test(inner) || /^#{1,3}\s/m.test(inner)
  return looksLikeWholeAnswer ? inner : text
}

export function parseResponse(rawText: string): ParsedResponse {
  // Normalize CRLF up front — every fence/marker regex below assumes a bare \n
  // right after the opening ``` or marker. A model reply with Windows line endings
  // (observed in practice) would otherwise match NONE of them, silently falling
  // through as one inert text block with no patch/full detection at all.
  const text = rawText.replace(/\r\n/g, '\n')
  const outerUnwrapped = unwrapAccidentalOuterFence(text)
  // Models sometimes wrap <<<PATCH/INSERT ...>>>...<<<END>>> markers in a ``` fence
  // (e.g. mimicking the Full-Replace example format). Without this, the fenced-code
  // alternative below would match first and swallow the whole thing as one inert
  // "full/text" block — hiding the real patch and its Apply button. Only unwraps
  // when the ENTIRE fence content is patch/insert blocks, so a genuine code sample
  // that merely mentions "<<<PATCH" in passing is left alone.
  const unwrapped = outerUnwrapped.replace(
    /```[\w]*\n((?:\s*<<<(?:PATCH|INSERT)\b[\s\S]*?<<<END>>>\s*)+)```/g,
    '$1',
  )
  const triggerRun = unwrapped.includes('<<RUN_TEST>>')
  const work = unwrapped.replace(/<<RUN_TEST>>/g, '').trimEnd()

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
      if (rawLang === 'diff' || rawLang === 'udiff' || rawLang === 'patch') {
        const hunks = parseUnifiedDiff(code, 'script')
        if (hunks.length > 0) {
          for (const block of hunks) segments.push({ type: 'diffhunk', block })
          continue
        }
        // fell through — no recognizable hunks, show as inert text rather than silently dropping it
      }
      const target: FullBlock['target'] =
        rawLang === 'python' ? 'script' : rawLang === 'json' ? 'config' : 'other'
      segments.push({ type: 'full', block: { kind: 'full', target, lang: rawLang || 'text', code } })
    }
  }

  const tail = work.slice(lastIndex)
  if (tail.trim()) segments.push({ type: 'text', content: tail })

  return { segments, triggerRun }
}

// ─── Structured-proposal builder ───────────────────────────────────────────────

// Bulletproof alternative to parseResponse's regex-guessing: proposals arrive as
// already-structured tool-call arguments (validated/parsed by the LLM SDK, not by
// us), so there is no textual convention for the model to get wrong — nothing to
// unwrap, no fence/line-ending format to match. Only the RUN_TEST marker and the
// answer text itself still need scanning; everything change-shaped is exact.
export function buildParsedResponse(answer: string, proposals: LLMAssistantProposal[] | null | undefined): ParsedResponse {
  const triggerRun = answer.includes('<<RUN_TEST>>')
  const text = answer.replace(/<<RUN_TEST>>/g, '').trim()

  const segments: Segment[] = []
  if (text) segments.push({ type: 'text', content: text })

  for (const p of proposals ?? []) {
    if (p.type === 'patch' && typeof p.search_text === 'string' && typeof p.replace_text === 'string') {
      segments.push({
        type: 'diffhunk',
        block: { kind: 'diffhunk', target: p.target, searchText: p.search_text, replaceText: p.replace_text },
      })
    } else if (p.type === 'full' && typeof p.content === 'string') {
      segments.push({
        type: 'full',
        block: { kind: 'full', target: p.target, lang: p.target === 'script' ? 'python' : 'json', code: p.content },
      })
    }
  }

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
