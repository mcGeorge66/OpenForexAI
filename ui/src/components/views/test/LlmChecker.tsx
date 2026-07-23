import { useEffect, useMemo, useRef, useState } from 'react'
import { Bot, Check, Copy, Database, Download, Send, User, X } from 'lucide-react'
import { api, type LlmCheckerMessage } from '@/api/client'
import { useTools } from '@/hooks/useTools'
import { useAgents } from '@/hooks/useAgents'

type ChatRole = 'user' | 'assistant'

interface ChatMessage {
  id: string
  role: ChatRole
  content: string
  timestamp: string
}

interface AgentDraftConfig {
  broker?: string
  pair?: string
  system_prompt?: string
  allowed_tools?: string[]
}

const DEFAULT_SYSTEM_PROMPT = 'You are a helpful assistant. Use tools when necessary.'

function now(): string {
  return new Date().toISOString().replace('T', ' ').substring(11, 19) + ' UTC'
}

function asPretty(value: unknown): string {
  if (typeof value === 'string') return value
  try {
    return JSON.stringify(value, null, 2)
  } catch {
    return String(value)
  }
}

function short(value: unknown, max = 260): string {
  const t = asPretty(value).replace(/\s+/g, ' ').trim()
  return t.length > max ? `${t.slice(0, max)} ...` : t
}

interface PromptEditorWindowProps {
  value: string
  onChange: (value: string) => void
  onTakeOver: () => void
  onClose: () => void
}

function PromptEditorWindow({ value, onChange, onTakeOver, onClose }: PromptEditorWindowProps) {
  const [pos, setPos] = useState(() => {
    const w = Math.min(860, window.innerWidth - 40)
    const h = Math.min(560, window.innerHeight - 40)
    return {
      x: Math.round((window.innerWidth - w) / 2),
      y: Math.round((window.innerHeight - h) / 2),
    }
  })
  const containerRef = useRef<HTMLDivElement | null>(null)
  const dragging = useRef(false)
  const dragOrigin = useRef({ mx: 0, my: 0, x: 0, y: 0 })

  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    el.style.width = `${Math.min(860, window.innerWidth - 40)}px`
    el.style.height = `${Math.min(560, window.innerHeight - 40)}px`
  }, [])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  useEffect(() => {
    const onMove = (e: MouseEvent) => {
      if (!dragging.current) return
      const { mx, my, x, y } = dragOrigin.current
      setPos({
        x: Math.max(0, x + e.clientX - mx),
        y: Math.max(0, y + e.clientY - my),
      })
    }
    const onUp = () => {
      dragging.current = false
    }
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
    return () => {
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
    }
  }, [])

  const startDrag = (e: React.MouseEvent) => {
    dragOrigin.current = { mx: e.clientX, my: e.clientY, x: pos.x, y: pos.y }
    dragging.current = true
    e.preventDefault()
  }

  return (
    <div className="fixed inset-0 z-50 bg-black/25">
      <div
        ref={containerRef}
        style={{
          position: 'fixed',
          left: pos.x,
          top: pos.y,
          minWidth: 420,
          minHeight: 260,
          resize: 'both',
          overflow: 'hidden',
          zIndex: 9999,
        }}
        className="flex flex-col bg-gray-900 border border-gray-600 rounded-lg shadow-2xl"
      >
        <div
          onMouseDown={startDrag}
          className="flex items-center justify-between px-3 py-2 bg-gray-800 border-b border-gray-600 rounded-t-lg cursor-move select-none flex-shrink-0"
        >
          <div className="text-xs text-gray-300">System Prompt Editor</div>
          <div className="flex items-center gap-2">
            <button
              onMouseDown={e => e.stopPropagation()}
              onClick={onTakeOver}
              className="px-2 py-1 text-xs rounded bg-emerald-700 text-white hover:bg-emerald-600"
              title="Take over"
            >
              Take over
            </button>
            <button
              onMouseDown={e => e.stopPropagation()}
              onClick={onClose}
              className="text-gray-500 hover:text-white transition-colors"
              title="Close (Esc)"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        <div className="flex-1 p-3 bg-gray-950">
          <textarea
            value={value}
            onChange={e => onChange(e.target.value)}
            className="w-full h-full resize-none bg-gray-900 text-gray-200 text-sm rounded px-3 py-2 border border-gray-700 focus:outline-none focus:border-emerald-500"
          />
        </div>
      </div>
    </div>
  )
}

export function LlmChecker() {
  const { tools, loading: toolsLoading, error: toolsError } = useTools()
  const { agents } = useAgents()

  const [llmOptions, setLlmOptions] = useState<string[]>([])
  const [brokerOptions, setBrokerOptions] = useState<string[]>([])
  const [contextError, setContextError] = useState<string | null>(null)
  const [agentConfigById, setAgentConfigById] = useState<Record<string, AgentDraftConfig>>({})

  const [selectedLlm, setSelectedLlm] = useState('')
  const [agentId, setAgentId] = useState('')
  const [brokerName, setBrokerName] = useState('')
  const [pair, setPair] = useState('')

  const [systemPrompt, setSystemPrompt] = useState(DEFAULT_SYSTEM_PROMPT)
  const [baseContext, setBaseContext] = useState('')
  const [promptEditorOpen, setPromptEditorOpen] = useState(false)
  const [promptEditorValue, setPromptEditorValue] = useState('')
  const [temperature, setTemperature] = useState('')
  const [maxTokens, setMaxTokens] = useState('')
  const [maxToolTurns, setMaxToolTurns] = useState('8')

  const [reasoningEffort, setReasoningEffort] = useState('')
  const [toolFilter, setToolFilter] = useState('')
  const [enabledTools, setEnabledTools] = useState<string[]>([])

  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [trace, setTrace] = useState<Array<Record<string, unknown>>>([])
  const [lastMeta, setLastMeta] = useState<{ tokens: number; stop: string } | null>(null)
  const [copiedId, setCopiedId] = useState<string | null>(null)
  const [kbPushing, setKbPushing] = useState(false)
  const [kbStatus, setKbStatus] = useState<string | null>(null)

  useEffect(() => {
    api.llmContextGet('llm_checker.md')
      .then(r => setBaseContext(r.content))
      .catch(() => { /* file may not exist yet */ })
  }, [])

  useEffect(() => {
    api.getModuleNames('llm')
      .then(resp => {
        setLlmOptions(resp.names)
        setSelectedLlm(prev => prev || resp.names[0] || '')
      })
      .catch(err => setContextError(String(err)))

    api.getModuleNames('broker')
      .then(resp => setBrokerOptions(resp.names))
      .catch(err => setContextError(String(err)))

    api.getSystemConfig()
      .then(cfg => {
        const agentsRaw = (cfg.agents ?? {}) as Record<string, unknown>
        const map: Record<string, AgentDraftConfig> = {}
        for (const [id, v] of Object.entries(agentsRaw)) {
          if (!v || typeof v !== 'object') continue
          const a = v as Record<string, unknown>
          map[id] = {
            broker: typeof a.broker === 'string' ? a.broker : undefined,
            pair: typeof a.pair === 'string' ? a.pair.toUpperCase() : undefined,
            system_prompt: typeof a.system_prompt === 'string' ? a.system_prompt : undefined,
            allowed_tools: Array.isArray((a.tool_config as Record<string, unknown> | undefined)?.allowed_tools)
              ? ((a.tool_config as Record<string, unknown>).allowed_tools as unknown[])
                  .filter((x): x is string => typeof x === 'string')
              : undefined,
          }
        }
        setAgentConfigById(map)
      })
      .catch(err => setContextError(String(err)))
  }, [])

  useEffect(() => {
    if (!agentId) return
    const cfg = agentConfigById[agentId]
    if (!cfg) return
    setBrokerName(cfg.broker ?? '')
    setPair(cfg.pair ?? '')
    setSystemPrompt(cfg.system_prompt ?? DEFAULT_SYSTEM_PROMPT)
    setEnabledTools(cfg.allowed_tools ?? [])
  }, [agentId, agentConfigById])

  useEffect(() => {
    if (!selectedLlm) {
      setTemperature('')
      setMaxTokens('')
      return
    }
    api.getModuleConfigRaw('llm', selectedLlm)
      .then(cfg => {
        const t = typeof cfg.temperature === 'number' ? String(cfg.temperature) : ''
        const m = typeof cfg.max_tokens === 'number' ? String(cfg.max_tokens) : ''
        setTemperature(t)
        setMaxTokens(m)
      })
      .catch(err => setContextError(String(err)))
  }, [selectedLlm])

  const filteredTools = useMemo(() => {
    const q = toolFilter.trim().toLowerCase()
    if (!q) return tools
    return tools.filter(t => t.name.toLowerCase().includes(q) || t.description.toLowerCase().includes(q))
  }, [toolFilter, tools])

  const toggleTool = (name: string) => {
    setEnabledTools(prev => (prev.includes(name) ? prev.filter(t => t !== name) : [...prev, name]))
  }

  const selectAllVisible = () => {
    const names = filteredTools.map(t => t.name)
    setEnabledTools(prev => Array.from(new Set([...prev, ...names])))
  }

  const clearVisible = () => {
    const visible = new Set(filteredTools.map(t => t.name))
    setEnabledTools(prev => prev.filter(name => !visible.has(name)))
  }

  const clearChat = () => {
    setMessages([])
    setTrace([])
    setLastMeta(null)
    setKbStatus(null)
  }

  const copyMessage = (msg: ChatMessage) => {
    void navigator.clipboard.writeText(msg.content).then(() => {
      setCopiedId(msg.id)
      setTimeout(() => setCopiedId(null), 1800)
    })
  }

  const exportMarkdown = () => {
    const date = new Date().toISOString().substring(0, 10)
    const lines: string[] = [
      `# LLM Checker — ${date}`,
      ``,
      `**LLM:** ${selectedLlm || '—'}  `,
      `**System Prompt:** ${systemPrompt.substring(0, 120)}${systemPrompt.length > 120 ? '...' : ''}`,
      ``,
      `---`,
      ``,
    ]
    for (const msg of messages) {
      const role = msg.role === 'user' ? '**User**' : '**Assistant**'
      lines.push(`### ${role} — ${msg.timestamp}`)
      lines.push(``)
      lines.push(msg.content)
      lines.push(``)
      lines.push(`---`)
      lines.push(``)
    }
    const blob = new Blob([lines.join('\n')], { type: 'text/markdown' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `llm-checker-${date}.md`
    a.click()
    URL.revokeObjectURL(url)
  }

  const pushToKnowledgeBase = async () => {
    if (messages.length === 0 || kbPushing) return
    setKbPushing(true)
    setKbStatus(null)
    try {
      const date = new Date().toISOString().substring(0, 16).replace('T', ' ')
      const lines: string[] = []
      for (const msg of messages) {
        const role = msg.role === 'user' ? '**User**' : '**Assistant**'
        lines.push(`### ${role} — ${msg.timestamp}\n`)
        lines.push(msg.content + '\n')
        lines.push('---\n')
      }
      await api.kbCreateDocument({
        title: `LLM Checker — ${selectedLlm} — ${date}`,
        content: lines.join('\n'),
        tags: ['llm-checker', selectedLlm].filter(Boolean) as unknown as string,
        parent_id: null,
        is_folder: 0,
        sort_order: 0,
      })
      setKbStatus('ok')
    } catch (err) {
      setKbStatus(`Fehler: ${String(err)}`)
    } finally {
      setKbPushing(false)
    }
  }

  const send = async () => {
    if (!selectedLlm || !input.trim() || sending) return

    const userMessage: ChatMessage = {
      id: `u-${Date.now()}`,
      role: 'user',
      content: input.trim(),
      timestamp: now(),
    }

    const nextMessages = [...messages, userMessage]
    setMessages(nextMessages)
    setInput('')
    setSending(true)

    const payloadMessages: LlmCheckerMessage[] = nextMessages.map(m => ({
      role: m.role,
      content: m.content,
    }))

    const trimmedTemp = temperature.trim()
    const trimmedMaxTokens = maxTokens.trim()
    const trimmedMaxToolTurns = maxToolTurns.trim()
    const parsedTemp = trimmedTemp ? Number(trimmedTemp) : undefined
    const parsedMaxTokens = trimmedMaxTokens ? Number(trimmedMaxTokens) : undefined
    const parsedMaxToolTurns = trimmedMaxToolTurns ? Number(trimmedMaxToolTurns) : undefined

    if (parsedTemp !== undefined && Number.isNaN(parsedTemp)) {
      setMessages(prev => [...prev, {
        id: `e-${Date.now()}`,
        role: 'assistant',
        content: 'Error: Temperature must be a number.',
        timestamp: now(),
      }])
      setSending(false)
      return
    }
    if (parsedMaxTokens !== undefined && Number.isNaN(parsedMaxTokens)) {
      setMessages(prev => [...prev, {
        id: `e-${Date.now()}`,
        role: 'assistant',
        content: 'Error: Max Tokens must be a number.',
        timestamp: now(),
      }])
      setSending(false)
      return
    }
    if (parsedMaxToolTurns !== undefined && Number.isNaN(parsedMaxToolTurns)) {
      setMessages(prev => [...prev, {
        id: `e-${Date.now()}`,
        role: 'assistant',
        content: 'Error: Max Tool Turns must be a number.',
        timestamp: now(),
      }])
      setSending(false)
      return
    }

    try {
      const effectiveSystemPrompt = baseContext.trim()
        ? `${baseContext.trim()}\n\n---\n\n${systemPrompt}`
        : systemPrompt

      const resp = await api.runLlmChecker({
        llm_name: selectedLlm,
        messages: payloadMessages,
        enabled_tools: enabledTools,
        system_prompt: effectiveSystemPrompt,
        temperature: parsedTemp,
        max_tokens: parsedMaxTokens,
        max_tool_turns: parsedMaxToolTurns,
        agent_id: agentId || null,
        broker_name: brokerName || null,
        pair: pair.trim() ? pair.trim().toUpperCase() : null,
        reasoning_effort: reasoningEffort || null,
      })

      const assistantMessage: ChatMessage = {
        id: `a-${Date.now()}`,
        role: 'assistant',
        content: resp.final_text || '(empty response)',
        timestamp: now(),
      }
      setMessages(prev => [...prev, assistantMessage])
      setTrace(resp.trace)
      setLastMeta({ tokens: resp.total_tokens, stop: resp.stop_reason })
    } catch (err) {
      const assistantError: ChatMessage = {
        id: `e-${Date.now()}`,
        role: 'assistant',
        content: `Error: ${String(err)}`,
        timestamp: now(),
      }
      setMessages(prev => [...prev, assistantError])
      setTrace([{ type: 'error', message: String(err) }])
      setLastMeta(null)
    } finally {
      setSending(false)
    }
  }

  const onInputKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      void send()
    }
  }

  return (
    <div className="flex flex-col h-full">
      <div className="flex-1 min-h-0 grid grid-cols-1 xl:grid-cols-2">
        <section className="flex flex-col min-h-0 border-r border-gray-700">
          <div className="px-4 py-2 bg-gray-900 border-b border-gray-700 flex items-center gap-3 flex-wrap">
            <span className="text-sm text-gray-200 font-medium">LLM Checker</span>
            <span className="text-xs text-white">LLM: {selectedLlm || '— none —'}</span>
            <div className="ml-auto flex items-center gap-2">
              {kbStatus === 'ok' && (
                <span className="text-xs text-emerald-400">In KB gespeichert</span>
              )}
              {kbStatus && kbStatus !== 'ok' && (
                <span className="text-xs text-red-400">{kbStatus}</span>
              )}
              <button
                onClick={exportMarkdown}
                disabled={messages.length === 0}
                title="Verlauf als Markdown-Datei speichern"
                className="flex items-center gap-1 text-xs px-2.5 py-1 rounded border border-blue-700 bg-blue-900/30 text-blue-300 hover:bg-blue-900/60 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              >
                <Download className="w-3 h-3" />
                Export .md
              </button>
              <button
                onClick={() => void pushToKnowledgeBase()}
                disabled={messages.length === 0 || kbPushing}
                title="Gesamten Verlauf in die Knowledge Base schieben"
                className="flex items-center gap-1 text-xs px-2.5 py-1 rounded border border-violet-700 bg-violet-900/30 text-violet-300 hover:bg-violet-900/60 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              >
                <Database className="w-3 h-3" />
                {kbPushing ? 'Speichern...' : '→ KB'}
              </button>
              <button
                onClick={clearChat}
                disabled={messages.length === 0}
                className="flex items-center gap-1 text-xs px-2.5 py-1 rounded border border-red-700 bg-red-900/30 text-red-400 hover:bg-red-900/60 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              >
                Clear chat
              </button>
            </div>
          </div>

          <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
            {messages.length === 0 && (
              <div className="text-center text-gray-600 mt-16 text-sm">
                Select an LLM, enable tools, and start a test dialog.
                <br />
                <span className="text-xs text-white">Enter to send, Shift+Enter for newline</span>
              </div>
            )}
            {messages.map(msg => (
              <div
                key={msg.id}
                className={`flex gap-3 ${msg.role === 'user' ? 'flex-row-reverse' : ''}`}
              >
                <div className={`flex-shrink-0 w-7 h-7 rounded-full flex items-center justify-center ${
                  msg.role === 'user' ? 'bg-emerald-800' : 'bg-blue-900'
                }`}>
                  {msg.role === 'user'
                    ? <User className="w-4 h-4 text-emerald-300" />
                    : <Bot className="w-4 h-4 text-blue-300" />}
                </div>
                <div className={`max-w-2xl ${msg.role === 'user' ? 'items-end' : 'items-start'} flex flex-col gap-1`}>
                  <div className="flex items-center gap-2">
                    <div className="text-xs text-white">{msg.timestamp}</div>
                    <button
                      onClick={() => copyMessage(msg)}
                      title="Copy"
                      className="flex items-center gap-1 text-xs text-white hover:text-white transition-colors"
                    >
                      {copiedId === msg.id
                        ? <><Check className="w-3 h-3 text-emerald-400" /><span className="text-emerald-400">Copied</span></>
                        : <><Copy className="w-3 h-3" />Copy</>
                      }
                    </button>
                  </div>
                  <div className={`rounded-lg px-3 py-2 text-sm whitespace-pre-wrap break-words ${
                    msg.role === 'user'
                      ? 'bg-emerald-900/50 text-emerald-100'
                      : 'bg-gray-800 text-gray-200'
                  }`}>
                    {msg.content}
                  </div>
                </div>
              </div>
            ))}

            {sending && (
              <div className="flex gap-3">
                <div className="flex-shrink-0 w-7 h-7 rounded-full bg-blue-900 flex items-center justify-center">
                  <Bot className="w-4 h-4 text-blue-300" />
                </div>
                <div className="bg-gray-800 rounded-lg px-3 py-2 text-sm text-gray-400 animate-pulse">
                  Running LLM + tool loop...
                </div>
              </div>
            )}
          </div>

          <div className="flex-shrink-0 px-4 py-3 bg-gray-900 border-t border-gray-700">
            <div className="flex gap-2 items-end">
              <textarea
                value={input}
                onChange={e => setInput(e.target.value)}
                onKeyDown={onInputKeyDown}
                placeholder={selectedLlm ? `Ask ${selectedLlm}...` : 'Select an LLM first'}
                disabled={!selectedLlm}
                rows={3}
                className="flex-1 resize-none bg-gray-800 text-gray-200 text-sm rounded px-3 py-2 border border-gray-600 focus:outline-none focus:border-emerald-500 placeholder-gray-600"
              />
              <button
                onClick={() => void send()}
                disabled={!selectedLlm || !input.trim() || sending}
                className="flex-shrink-0 flex items-center gap-1.5 px-4 py-2 bg-emerald-700 hover:bg-emerald-600 disabled:bg-gray-700 disabled:text-gray-500 text-white text-sm rounded transition-colors"
              >
                <Send className="w-4 h-4" />
                Send
              </button>
            </div>
            <p className="text-xs text-white mt-1">Enter to send, Shift+Enter for newline</p>
          </div>
        </section>

        <aside className="flex flex-col min-h-0 bg-gray-950">
          <div className="px-4 py-2 border-b border-gray-700 bg-gray-900">
            <h3 className="text-sm text-gray-200 font-medium">Session Configuration</h3>
          </div>

          <div className="flex-1 min-h-0 p-4 overflow-auto space-y-4">
            <div className="grid grid-cols-1 gap-3">
              <div>
                <label className="block text-xs text-white mb-1">LLM</label>
                <select
                  value={selectedLlm}
                  onChange={e => setSelectedLlm(e.target.value)}
                  className="w-full bg-gray-800 text-gray-200 text-sm rounded px-2 py-1.5 border border-gray-600 focus:outline-none focus:border-emerald-500"
                >
                  <option value="">— select llm —</option>
                  {llmOptions.map(name => (
                    <option key={name} value={name}>{name}</option>
                  ))}
                </select>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                <div>
                  <label className="block text-xs text-white mb-1">Agent (optional)</label>
                  <select
                    value={agentId}
                    onChange={e => setAgentId(e.target.value)}
                    className="w-full bg-gray-800 text-gray-200 text-xs rounded px-2 py-1.5 border border-gray-600 focus:outline-none focus:border-emerald-500"
                  >
                    <option value="">— none —</option>
                    {agents.map(a => (
                      <option key={a.agent_id} value={a.agent_id}>{a.agent_id}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-xs text-white mb-1">Broker (optional)</label>
                  <select
                    value={brokerName}
                    onChange={e => setBrokerName(e.target.value)}
                    className="w-full bg-gray-800 text-gray-200 text-xs rounded px-2 py-1.5 border border-gray-600 focus:outline-none focus:border-emerald-500"
                  >
                    <option value="">— none —</option>
                    {brokerOptions.map(name => (
                      <option key={name} value={name}>{name}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-xs text-white mb-1">Pair (optional)</label>
                  <input
                    value={pair}
                    onChange={e => setPair(e.target.value)}
                    placeholder="EURUSD"
                    className="w-full bg-gray-800 text-gray-200 text-xs rounded px-2 py-1.5 border border-gray-600 focus:outline-none focus:border-emerald-500"
                  />
                </div>
              </div>

              {baseContext && (
                <div className="rounded border border-blue-900/50 bg-blue-950/30 px-3 py-2 text-xs text-blue-300">
                  <span className="font-medium">Base context active:</span>
                  <span className="ml-1 text-blue-400">llm_checker.md</span>
                  <span className="text-blue-500 ml-1">— prepended to system prompt on every send. Edit in AI-Assistant → LLM Contexts.</span>
                </div>
              )}
              <div>
                <label className="block text-xs text-white mb-1">System Prompt</label>
                <textarea
                  value={systemPrompt}
                  onChange={e => setSystemPrompt(e.target.value)}
                  onDoubleClick={() => {
                    setPromptEditorValue(systemPrompt)
                    setPromptEditorOpen(true)
                  }}
                  rows={4}
                  className="w-full bg-gray-800 text-gray-200 text-xs rounded px-2 py-1.5 border border-gray-600 focus:outline-none focus:border-emerald-500"
                />
                <p className="text-[11px] text-white mt-1">Double-click to open large editor window.</p>
              </div>

              <div className="grid grid-cols-4 gap-3">
                <div>
                  <label className="block text-xs text-white mb-1">Temperature</label>
                  <input
                    value={temperature}
                    onChange={e => setTemperature(e.target.value)}
                    className="w-full bg-gray-800 text-gray-200 text-xs rounded px-2 py-1.5 border border-gray-600 focus:outline-none focus:border-emerald-500"
                  />
                </div>
                <div>
                  <label className="block text-xs text-white mb-1">Max Tokens</label>
                  <input
                    value={maxTokens}
                    onChange={e => setMaxTokens(e.target.value)}
                    className="w-full bg-gray-800 text-gray-200 text-xs rounded px-2 py-1.5 border border-gray-600 focus:outline-none focus:border-emerald-500"
                  />
                </div>
                <div>
                  <label className="block text-xs text-white mb-1">Max Tool Turns</label>
                  <input
                    value={maxToolTurns}
                    onChange={e => setMaxToolTurns(e.target.value)}
                    className="w-full bg-gray-800 text-gray-200 text-xs rounded px-2 py-1.5 border border-gray-600 focus:outline-none focus:border-emerald-500"
                  />
                </div>
                <div>
                  <label className="block text-xs text-white mb-1">Reasoning</label>
                  <select
                    value={reasoningEffort}
                    onChange={e => setReasoningEffort(e.target.value)}
                    className="w-full bg-gray-800 text-gray-200 text-xs rounded px-2 py-1.5 border border-gray-600 focus:outline-none focus:border-emerald-500"
                  >
                    <option value="">— off —</option>
                    <option value="low">low</option>
                    <option value="medium">medium</option>
                    <option value="high">high</option>
                  </select>
                </div>
              </div>

              <div className="border border-gray-700 rounded p-3 bg-gray-900/30 space-y-2">
                <div className="flex items-center gap-2">
                  <label className="text-xs text-white">Tools</label>
                  <input
                    value={toolFilter}
                    onChange={e => setToolFilter(e.target.value)}
                    placeholder="Filter tools..."
                    className="ml-auto bg-gray-800 text-gray-200 text-xs rounded px-2 py-1 border border-gray-600 focus:outline-none focus:border-emerald-500"
                  />
                </div>
                <div className="flex items-center gap-2">
                  <button onClick={selectAllVisible} className="text-xs px-2 py-1 rounded bg-gray-800 border border-gray-600 text-gray-200 hover:bg-gray-700">Select visible</button>
                  <button onClick={clearVisible} className="text-xs px-2 py-1 rounded bg-gray-800 border border-gray-600 text-gray-200 hover:bg-gray-700">Clear visible</button>
                  <span className="text-xs text-white ml-auto">Enabled: {enabledTools.length}</span>
                </div>
                <div className="max-h-52 overflow-auto space-y-1 pr-1">
                  {toolsLoading && <p className="text-xs text-white animate-pulse">Loading tools...</p>}
                  {toolsError && <p className="text-xs text-red-400">Error: {toolsError}</p>}
                  {!toolsLoading && filteredTools.map(t => {
                    const checked = enabledTools.includes(t.name)
                    return (
                      <label key={t.name} className="flex items-start gap-2 text-xs text-gray-300 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={checked}
                          onChange={() => toggleTool(t.name)}
                          className="mt-0.5"
                        />
                        <span>
                          <span className="font-mono text-emerald-300">{t.name}</span>
                          <span className="text-gray-500"> - {short(t.description, 120)}</span>
                        </span>
                      </label>
                    )
                  })}
                </div>
              </div>
            </div>

            {contextError && (
              <p className="text-xs text-red-400">{contextError}</p>
            )}

            <div className="border border-gray-700 rounded p-3 bg-gray-900/40">
              <div className="flex items-center justify-between mb-2">
                <h4 className="text-xs uppercase tracking-wider text-white">LLM ↔ Tool Trace</h4>
                {lastMeta && (
                  <span className="text-xs text-white">tokens: {lastMeta.tokens} | stop: {lastMeta.stop}</span>
                )}
              </div>
              <div className="max-h-80 overflow-auto space-y-2">
                {trace.length === 0 && (
                  <p className="text-xs text-white">No trace yet. Send a message to run a test cycle.</p>
                )}
                {trace.map((item, idx) => {
                  const type = String(item.type ?? 'event')
                  if (type === 'llm_response') {
                    const toolCalls = Array.isArray(item.tool_calls) ? item.tool_calls.length : 0
                    return (
                      <div key={`trace-${idx}`} className="text-xs border border-gray-700 rounded p-2 bg-gray-950/60 space-y-1">
                        <div className="text-blue-300">LLM response (turn {String(item.turn ?? '?')})</div>
                        <div className="text-gray-400">stop_reason: {String(item.stop_reason ?? '')} | tools requested: {toolCalls}</div>
                        <div className="text-gray-300 whitespace-pre-wrap">{short(item.content ?? '', 380)}</div>
                      </div>
                    )
                  }
                  if (type === 'tool_result') {
                    return (
                      <div key={`trace-${idx}`} className="text-xs border border-gray-700 rounded p-2 bg-gray-950/60 space-y-1">
                        <div className={String(item.is_error) === 'true' ? 'text-red-300' : 'text-emerald-300'}>
                          Tool {String(item.tool ?? '')} (turn {String(item.turn ?? '?')})
                        </div>
                        <div className="text-gray-400">args: {short(item.arguments ?? {}, 220)}</div>
                        <div className="text-gray-300">result: {short(item.result ?? {}, 320)}</div>
                      </div>
                    )
                  }
                  return (
                    <div key={`trace-${idx}`} className="text-xs border border-gray-700 rounded p-2 bg-gray-950/60 text-gray-300">
                      {short(item, 420)}
                    </div>
                  )
                })}
              </div>
            </div>
          </div>
        </aside>
      </div>

      {promptEditorOpen && (
        <PromptEditorWindow
          value={promptEditorValue}
          onChange={setPromptEditorValue}
          onTakeOver={() => {
            setSystemPrompt(promptEditorValue)
            setPromptEditorOpen(false)
          }}
          onClose={() => setPromptEditorOpen(false)}
        />
      )}
    </div>
  )
}


