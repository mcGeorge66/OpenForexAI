/**
 * AgentChat — select an agent and send free-text questions.
 *
 * Uses POST /agents/{id}/ask and shows the response in a chat-bubble style.
 */

import { useState } from 'react'
import { api } from '@/api/client'
import { useAgents } from '@/hooks/useAgents'
import { Send, Bot, User } from 'lucide-react'

interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  agentId?: string
  timestamp: string
}

function now(): string {
  return new Date().toISOString().replace('T', ' ').substring(11, 19) + ' UTC'
}

export function AgentChat() {
  const { agents, loading: agentsLoading } = useAgents()
  const [selectedAgent, setSelectedAgent] = useState<string>('')
  const [input, setInput] = useState('')
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [sending, setSending] = useState(false)
  const [timeout, setTimeout_] = useState(120)

  const send = async () => {
    if (!selectedAgent || !input.trim() || sending) return

    const question = input.trim()
    setInput('')
    setSending(true)

    const userMsg: ChatMessage = {
      id: `u-${Date.now()}`,
      role: 'user',
      content: question,
      timestamp: now(),
    }
    setMessages(prev => [...prev, userMsg])

    try {
      const resp = await api.askAgent(selectedAgent, question, timeout)
      const assistantMsg: ChatMessage = {
        id: `a-${Date.now()}`,
        role: 'assistant',
        content: resp.response || '(empty response)',
        agentId: resp.agent_id,
        timestamp: now(),
      }
      setMessages(prev => [...prev, assistantMsg])
    } catch (err) {
      const errMsg: ChatMessage = {
        id: `e-${Date.now()}`,
        role: 'assistant',
        content: `Error: ${String(err)}`,
        agentId: selectedAgent,
        timestamp: now(),
      }
      setMessages(prev => [...prev, errMsg])
    } finally {
      setSending(false)
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
      e.preventDefault()
      send()
    }
  }

  return (
    <div className="flex flex-col h-full">
      {/* Agent selector bar */}
      <div className="flex items-center gap-3 px-4 py-2 bg-gray-900 border-b border-gray-700 flex-shrink-0">
        <label className="text-xs text-gray-400 flex-shrink-0">Agent:</label>
        <select
          value={selectedAgent}
          onChange={e => setSelectedAgent(e.target.value)}
          disabled={agentsLoading}
          className="flex-1 max-w-xs bg-gray-800 text-gray-200 text-sm rounded px-2 py-1 border border-gray-600 focus:outline-none focus:border-emerald-500"
        >
          <option value="">— select agent —</option>
          {agents.map(a => (
            <option key={a.agent_id} value={a.agent_id}>{a.agent_id}</option>
          ))}
        </select>

        <label className="text-xs text-gray-400 flex-shrink-0 ml-4">Timeout (s):</label>
        <input
          type="number"
          min={5}
          max={300}
          value={timeout}
          onChange={e => setTimeout_(Number(e.target.value))}
          className="w-16 bg-gray-800 text-gray-200 text-sm rounded px-2 py-1 border border-gray-600 focus:outline-none focus:border-emerald-500"
        />

        <button
          onClick={() => setMessages([])}
          className="ml-auto text-xs text-gray-500 hover:text-gray-300 transition-colors"
        >
          Clear chat
        </button>
      </div>

      {/* Message list */}
      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
        {messages.length === 0 && (
          <div className="text-center text-gray-600 mt-16 text-sm">
            Select an agent and send a question.<br />
            <span className="text-xs text-gray-700">Ctrl+Enter to send quickly</span>
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
              <div className="flex items-baseline gap-2 text-xs text-gray-500">
                {msg.role === 'assistant' && msg.agentId && (
                  <span className="text-blue-400">{msg.agentId}</span>
                )}
                <span>{msg.timestamp}</span>
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
              Waiting for {selectedAgent}…
            </div>
          </div>
        )}
      </div>

      {/* Input area */}
      <div className="flex-shrink-0 px-4 py-3 bg-gray-900 border-t border-gray-700">
        <div className="flex gap-2 items-end">
          <textarea
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={selectedAgent ? `Ask ${selectedAgent}…` : 'Select an agent first'}
            disabled={!selectedAgent || sending}
            rows={3}
            className="flex-1 resize-none bg-gray-800 text-gray-200 text-sm rounded px-3 py-2 border border-gray-600 focus:outline-none focus:border-emerald-500 placeholder-gray-600"
          />
          <button
            onClick={send}
            disabled={!selectedAgent || !input.trim() || sending}
            className="flex-shrink-0 flex items-center gap-1.5 px-4 py-2 bg-emerald-700 hover:bg-emerald-600 disabled:bg-gray-700 disabled:text-gray-500 text-white text-sm rounded transition-colors"
          >
            <Send className="w-4 h-4" />
            Send
          </button>
        </div>
        <p className="text-xs text-gray-600 mt-1">Ctrl+Enter to send</p>
      </div>
    </div>
  )
}
