/**
 * EventTestModal — lets users compose and inject a test event into the bus.
 *
 * Loads the event_schemas.json5 to show which fields are required per EventType.
 * Validates client-side before injecting via POST /events.
 */
import { useEffect, useState } from 'react'
import { api, type EventSchemaEntry } from '@/api/client'
import { AlertCircle, Check, Loader2, Play, X } from 'lucide-react'

interface Props {
  /** Pre-selected event type (e.g. from the agent's configured triggers) */
  defaultEventType?: string
  /** Source agent ID to pre-fill */
  defaultSourceAgentId?: string
  onClose: () => void
}

export function EventTestModal({ defaultEventType = '', defaultSourceAgentId = 'management_api', onClose }: Props) {
  const [schemas, setSchemas] = useState<Record<string, EventSchemaEntry>>({})
  const [loadingSchemas, setLoadingSchemas] = useState(true)

  const [eventType, setEventType] = useState(defaultEventType)
  const [sourceAgentId, setSourceAgentId] = useState(defaultSourceAgentId)
  const [payloadText, setPayloadText] = useState('{}')

  const [sending, setSending] = useState(false)
  const [result, setResult] = useState<{ ok: boolean; message: string } | null>(null)

  useEffect(() => {
    api.getEventSchemas()
      .then(s => setSchemas(s))
      .catch(() => setSchemas({}))
      .finally(() => setLoadingSchemas(false))
  }, [])

  const requiredFields: string[] = schemas[eventType]?.required ?? []

  function validate(): string | null {
    if (!eventType.trim()) return 'Event type is required'
    if (!sourceAgentId.trim()) return 'Source agent ID is required'
    let payload: unknown
    try {
      payload = JSON.parse(payloadText)
    } catch {
      return 'Payload is not valid JSON'
    }
    if (typeof payload !== 'object' || payload === null || Array.isArray(payload)) {
      return 'Payload must be a JSON object'
    }
    const p = payload as Record<string, unknown>
    const missing = requiredFields.filter(f => !(f in p))
    if (missing.length > 0) {
      return `Missing required fields for ${eventType}: ${missing.join(', ')}`
    }
    return null
  }

  async function handleSend() {
    const err = validate()
    if (err) {
      setResult({ ok: false, message: err })
      return
    }
    setSending(true)
    setResult(null)
    try {
      const payload = JSON.parse(payloadText) as Record<string, unknown>
      const resp = await api.injectEvent({
        event_type: eventType,
        source_agent_id: sourceAgentId,
        payload,
      })
      setResult({ ok: true, message: `Event injected — id: ${resp.message_id}` })
    } catch (e) {
      setResult({ ok: false, message: String(e) })
    } finally {
      setSending(false)
    }
  }

  const validationError = eventType ? validate() : null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="w-full max-w-lg bg-gray-950 border border-gray-700 rounded-xl overflow-hidden shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 bg-gray-900 border-b border-gray-700">
          <span className="text-sm font-semibold text-emerald-400">Test Event</span>
          <button onClick={onClose} className="text-gray-500 hover:text-gray-300">
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="p-4 space-y-4">
          {/* Event type selector */}
          <div>
            <label className="block text-xs text-white mb-1">Event Type</label>
            {loadingSchemas ? (
              <div className="flex items-center gap-2 text-white text-xs">
                <Loader2 className="w-3 h-3 animate-spin" /> Loading schemas…
              </div>
            ) : (
              <select
                value={eventType}
                onChange={e => setEventType(e.target.value)}
                className="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-sm text-gray-200 focus:outline-none focus:border-emerald-600"
              >
                <option value="">— select event type —</option>
                {Object.keys(schemas)
                  .filter(k => !k.startsWith('_'))
                  .sort()
                  .map(k => (
                    <option key={k} value={k}>{k}</option>
                  ))}
              </select>
            )}
          </div>

          {/* Required fields hint */}
          {eventType && requiredFields.length > 0 && (
            <div className="text-xs text-white bg-gray-900 rounded px-3 py-2">
              Required payload fields:&nbsp;
              <span className="text-orange-400 font-mono">{requiredFields.join(', ')}</span>
            </div>
          )}
          {eventType && requiredFields.length === 0 && (
            <div className="text-xs text-white">No required payload fields for this event type.</div>
          )}

          {/* Source agent */}
          <div>
            <label className="block text-xs text-white mb-1">Source Agent ID</label>
            <input
              type="text"
              value={sourceAgentId}
              onChange={e => setSourceAgentId(e.target.value)}
              className="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-sm text-gray-200 focus:outline-none focus:border-emerald-600"
            />
          </div>

          {/* Payload */}
          <div>
            <label className="block text-xs text-white mb-1">Payload (JSON)</label>
            <textarea
              rows={6}
              value={payloadText}
              onChange={e => setPayloadText(e.target.value)}
              className="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-sm text-gray-200 font-mono focus:outline-none focus:border-emerald-600 resize-none"
              spellCheck={false}
            />
          </div>

          {/* Validation warning */}
          {validationError && (
            <div className="flex items-center gap-2 text-orange-400 text-xs">
              <AlertCircle className="w-3.5 h-3.5 flex-shrink-0" />
              {validationError}
            </div>
          )}

          {/* Result */}
          {result && (
            <div className={`flex items-center gap-2 text-xs rounded px-3 py-2 ${result.ok ? 'bg-emerald-900/40 text-emerald-400' : 'bg-red-900/40 text-red-400'}`}>
              {result.ok ? <Check className="w-3.5 h-3.5 flex-shrink-0" /> : <AlertCircle className="w-3.5 h-3.5 flex-shrink-0" />}
              {result.message}
            </div>
          )}

          {/* Actions */}
          <div className="flex items-center justify-end gap-2 pt-1">
            <button
              onClick={onClose}
              className="px-3 py-1.5 rounded border border-gray-700 bg-gray-900 text-gray-300 hover:text-white text-sm"
            >
              Close
            </button>
            <button
              onClick={() => void handleSend()}
              disabled={sending || !!validationError || !eventType}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded bg-emerald-700 hover:bg-emerald-600 disabled:opacity-50 text-white text-sm"
            >
              {sending ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Play className="w-3.5 h-3.5" />}
              Inject Event
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
