/**
 * Header — top bar: app name + version, live clock, last-event timestamp.
 */

import { useEffect, useState } from 'react'
import { api } from '@/api/client'
import { Activity, Wifi, WifiOff } from 'lucide-react'

interface HeaderProps {
  lastUpdate: string | null
  connected: boolean
}

function formatClock(date: Date): string {
  return date.toISOString().replace('T', ' ').substring(0, 19) + ' UTC'
}

function formatLastUpdate(iso: string | null): string {
  if (!iso) return '—'
  try {
    const d = new Date(iso)
    return d.toISOString().replace('T', ' ').substring(11, 19) + ' UTC'
  } catch {
    return iso
  }
}

export function Header({ lastUpdate, connected }: HeaderProps) {
  const [version, setVersion] = useState<string>('…')
  const [clock, setClock] = useState<string>(formatClock(new Date()))

  useEffect(() => {
    api.getVersion()
      .then(v => setVersion(v.version))
      .catch(() => setVersion('?'))
  }, [])

  useEffect(() => {
    const timer = setInterval(() => setClock(formatClock(new Date())), 1000)
    return () => clearInterval(timer)
  }, [])

  return (
    <header className="flex items-center justify-between px-4 py-2 bg-gray-900 border-b border-gray-700 flex-shrink-0">
      <div className="flex items-center gap-3">
        <Activity className="w-5 h-5 text-emerald-400" />
        <span className="font-semibold text-white text-base tracking-wide">
          OpenForexAI
        </span>
        <span className="text-xs text-gray-400 bg-gray-800 px-2 py-0.5 rounded">
          v{version}
        </span>
      </div>

      <div className="flex items-center gap-6 text-xs text-gray-400">
        {/* WebSocket connection indicator */}
        <div className="flex items-center gap-1.5">
          {connected
            ? <Wifi className="w-3.5 h-3.5 text-emerald-400" />
            : <WifiOff className="w-3.5 h-3.5 text-red-400" />}
          <span className={connected ? 'text-emerald-400' : 'text-red-400'}>
            {connected ? 'Live' : 'Disconnected'}
          </span>
        </div>

        {/* Last event timestamp */}
        <div className="flex items-center gap-1.5">
          <span className="text-gray-500">Last:</span>
          <span className="font-mono">{formatLastUpdate(lastUpdate)}</span>
        </div>

        {/* Live clock */}
        <div className="font-mono text-gray-300">{clock}</div>
      </div>
    </header>
  )
}
