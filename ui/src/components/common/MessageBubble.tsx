/**
 * MessageBubble — renders one assistant/user chat message, including inline
 * full/patch code-block actions (copy, apply). Split out from assistantShared.tsx
 * (the parser/patch-engine/types) so that file only exports non-component values
 * and this one only exports the component — a Fast Refresh requirement.
 */
import { useState } from 'react'
import { Check, Copy, Pencil, FlaskConical, AlertTriangle } from 'lucide-react'
import { applyDiffHunk, applyPatch, parseResponse, renderInlineText, type AssistantMessage } from './assistantShared'

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
                  <span className="text-[10px] font-mono text-white">{block.lang} · vollständig</span>
                  <div className="flex items-center gap-2">
                    <button type="button" onClick={() => { void navigator.clipboard.writeText(block.code).then(() => markCopied(i)) }}
                      className="flex items-center gap-1 text-[10px] text-white hover:text-gray-300 transition-colors">
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
                      className="flex items-center gap-1 text-[10px] text-white hover:text-gray-300 transition-colors">
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

          if (seg.type === 'diffhunk') {
            const { block } = seg
            const targetLabel = block.target === 'script' ? 'Script' : 'Config'
            const canApply = block.target === 'script' || (block.target === 'config' && !!onApplyConfig)

            return (
              <div key={i} className="rounded border border-indigo-800/60 overflow-hidden">
                <div className="flex items-center justify-between px-2 py-1 bg-gray-900 border-b border-indigo-800/40">
                  <span className="text-[10px] font-mono text-indigo-400">diff {targetLabel}</span>
                  <div className="flex items-center gap-2">
                    <button type="button" onClick={() => { void navigator.clipboard.writeText(block.replaceText).then(() => markCopied(i)) }}
                      className="flex items-center gap-1 text-[10px] text-white hover:text-gray-300 transition-colors">
                      {copied[i] ? <><Check className="w-3 h-3 text-emerald-400" /><span className="text-emerald-400">Copied</span></> : <><Copy className="w-3 h-3" />Copy</>}
                    </button>
                    {canApply && !autoWrite && (
                      <button type="button" onClick={() => {
                        const source = block.target === 'script' ? currentScript : currentConfig
                        const { result, error } = applyDiffHunk(source, block)
                        if (error) { setPatchErrors(s => ({ ...s, [i]: error })); return }
                        if (block.target === 'script') onApplyScript(result)
                        if (block.target === 'config') onApplyConfig?.(result)
                        markApplied(i)
                        setPatchErrors(s => { const n = { ...s }; delete n[i]; return n })
                      }} className="flex items-center gap-1 text-[10px] text-indigo-400 hover:text-indigo-300 border border-indigo-700 rounded px-1.5 py-0.5 transition-colors">
                        {applied[i] ? <><Check className="w-3 h-3" />Applied</> : <><Pencil className="w-3 h-3" />Apply diff</>}
                      </button>
                    )}
                    {canApply && autoWrite && <span className="text-[10px] text-indigo-400 italic">auto-applied</span>}
                  </div>
                </div>
                <pre className="px-3 py-2 text-[11px] font-mono overflow-x-auto whitespace-pre bg-gray-950">
                  {block.searchText.split('\n').map((l, li) => <div key={`s${li}`} className="text-red-400">{`- ${l}`}</div>)}
                  {block.replaceText.split('\n').map((l, li) => <div key={`r${li}`} className="text-emerald-400">{`+ ${l}`}</div>)}
                </pre>
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
