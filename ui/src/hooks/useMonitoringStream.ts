/**
 * useMonitoringStream — React hook for the /ws/monitoring WebSocket.
 *
 * Opens a WebSocket connection to the FastAPI backend, appends incoming
 * MonitoringEvents to a ring buffer (max MAX_EVENTS), and reconnects
 * automatically if the connection drops.
 *
 * Usage:
 *   const { events, connected, lastUpdate, clear } = useMonitoringStream()
 *   const { events } = useMonitoringStream({ filter: ['llm_request', 'llm_response'] })
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import type { MonitoringEvent } from '@/api/client'

const MAX_EVENTS = 500
const RECONNECT_DELAY_MS = 3000

// WebSocket URL — in dev, Vite proxy forwards /ws → ws://127.0.0.1:8765
// In production, same host/port serves both HTTP and WS.
function wsUrl(filter?: string[]): string {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const host = window.location.host
  let url = `${protocol}//${host}/ws/monitoring`
  if (filter && filter.length > 0) {
    url += `?filter=${filter.join(',')}`
  }
  return url
}

interface UseMonitoringStreamOptions {
  /** Comma-joined list of event_type values to receive (all events if omitted) */
  filter?: string[]
  /** Whether the stream should be active (default true) */
  enabled?: boolean
}

interface UseMonitoringStreamResult {
  events: MonitoringEvent[]
  connected: boolean
  /** ISO timestamp of last received event, or null */
  lastUpdate: string | null
  clear: () => void
}

export function useMonitoringStream(
  opts: UseMonitoringStreamOptions = {},
): UseMonitoringStreamResult {
  const { filter, enabled = true } = opts

  const [events, setEvents] = useState<MonitoringEvent[]>([])
  const [connected, setConnected] = useState(false)
  const [lastUpdate, setLastUpdate] = useState<string | null>(null)

  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const mountedRef = useRef(true)
  const connectRef = useRef<() => void>(() => {})

  const clear = useCallback(() => setEvents([]), [])

  const connect = useCallback(() => {
    if (!mountedRef.current || !enabled) return

    const url = wsUrl(filter)
    const ws = new WebSocket(url)
    wsRef.current = ws

    ws.onopen = () => {
      if (mountedRef.current) setConnected(true)
    }

    ws.onmessage = (ev) => {
      try {
        const data = JSON.parse(ev.data as string)
        // Skip heartbeat pings
        if (data.type === 'ping') return

        const event = data as MonitoringEvent
        if (mountedRef.current) {
          setEvents(prev => {
            const next = [...prev, event]
            return next.length > MAX_EVENTS ? next.slice(next.length - MAX_EVENTS) : next
          })
          setLastUpdate(event.timestamp)
        }
      } catch {
        // ignore malformed messages
      }
    }

    ws.onclose = () => {
      if (mountedRef.current) {
        setConnected(false)
        // Reconnect after delay
        reconnectTimer.current = setTimeout(() => {
          connectRef.current()
        }, RECONNECT_DELAY_MS)
      }
    }

    ws.onerror = () => {
      ws.close()
    }
  }, [enabled, filter])

  useEffect(() => {
    connectRef.current = connect
  }, [connect])

  useEffect(() => {
    mountedRef.current = true
    if (enabled) connect()

    return () => {
      mountedRef.current = false
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current)
      if (wsRef.current) {
        wsRef.current.onclose = null // prevent reconnect on unmount
        wsRef.current.close()
      }
    }
  }, [connect, enabled])

  return { events, connected, lastUpdate, clear }
}
