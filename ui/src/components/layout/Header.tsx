/**
 * Header — top bar: app name + version, live clock, last-event timestamp.
 */

import { useEffect, useRef, useState } from 'react'
import { api } from '@/api/client'
import { Activity, Wifi, WifiOff } from 'lucide-react'

interface HeaderProps {
  lastUpdate: string | null
  connected: boolean
}

const TZ_OPTIONS = [
  { label: 'UTC−5', offset: -5 },
  { label: 'UTC−4', offset: -4 },
  { label: 'UTC−3', offset: -3 },
  { label: 'UTC−2', offset: -2 },
  { label: 'UTC−1', offset: -1 },
  { label: 'UTC',   offset:  0 },
  { label: 'UTC+1', offset:  1 },
  { label: 'UTC+2', offset:  2 },
  { label: 'UTC+3', offset:  3 },
  { label: 'UTC+4', offset:  4 },
  { label: 'UTC+5', offset:  5 },
  { label: 'UTC+6', offset:  6 },
  { label: 'UTC+7', offset:  7 },
  { label: 'UTC+8', offset:  8 },
  { label: 'UTC+9', offset:  9 },
  { label: 'UTC+10', offset: 10 },
  { label: 'UTC+11', offset: 11 },
  { label: 'UTC+12', offset: 12 },
]

const TZ_KEY = 'ofx_clock_tz_offset'

function loadOffset(): number {
  try {
    const raw = localStorage.getItem(TZ_KEY)
    if (raw !== null) {
      const n = parseInt(raw, 10)
      if (!isNaN(n) && n >= -12 && n <= 14) return n
    }
  } catch { /* ignore */ }
  return 0
}

function saveOffset(offset: number): void {
  try { localStorage.setItem(TZ_KEY, String(offset)) } catch { /* ignore */ }
}

function offsetLabel(offset: number): string {
  if (offset === 0) return 'UTC'
  return offset > 0 ? `UTC+${offset}` : `UTC${offset}`
}

function formatClock(date: Date, offset: number): string {
  const shifted = new Date(date.getTime() + offset * 3600_000)
  return shifted.toISOString().replace('T', ' ').substring(0, 19) + ' ' + offsetLabel(offset)
}

function formatLastUpdate(iso: string | null, offset: number): string {
  if (!iso) return '—'
  try {
    const d = new Date(iso)
    const shifted = new Date(d.getTime() + offset * 3600_000)
    return shifted.toISOString().substring(11, 19) + ' ' + offsetLabel(offset)
  } catch {
    return iso
  }
}

export function Header({ lastUpdate, connected }: HeaderProps) {
  const [version, setVersion] = useState<string>('…')
  const [tzOffset, setTzOffset] = useState<number>(loadOffset)
  const [clock, setClock] = useState<string>(() => formatClock(new Date(), loadOffset()))
  const [showTzPicker, setShowTzPicker] = useState(false)
  const pickerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    api.getVersion()
      .then(v => setVersion(v.version))
      .catch(() => setVersion('?'))
  }, [])

  useEffect(() => {
    const timer = setInterval(() => setClock(formatClock(new Date(), tzOffset)), 1000)
    return () => clearInterval(timer)
  }, [tzOffset])

  useEffect(() => {
    if (!showTzPicker) return
    function onClickOutside(e: MouseEvent) {
      if (pickerRef.current && !pickerRef.current.contains(e.target as Node)) {
        setShowTzPicker(false)
      }
    }
    document.addEventListener('mousedown', onClickOutside)
    return () => document.removeEventListener('mousedown', onClickOutside)
  }, [showTzPicker])

  function selectOffset(offset: number) {
    saveOffset(offset)
    setTzOffset(offset)
    setClock(formatClock(new Date(), offset))
    setShowTzPicker(false)
  }

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
          <span className="font-mono">{formatLastUpdate(lastUpdate, tzOffset)}</span>
        </div>

        {/* Live clock with timezone picker */}
        <div className="relative" ref={pickerRef}>
          <button
            className="font-mono text-gray-300 hover:text-white cursor-pointer"
            onClick={() => setShowTzPicker(v => !v)}
            title="Click to change timezone"
          >
            {clock}
          </button>

          {showTzPicker && (
            <div className="absolute right-0 top-full mt-1 z-50 bg-gray-800 border border-gray-600 rounded shadow-lg py-1 min-w-[100px]">
              {TZ_OPTIONS.map(opt => (
                <button
                  key={opt.offset}
                  className={`w-full text-left px-3 py-1 text-xs font-mono hover:bg-gray-700 ${
                    opt.offset === tzOffset ? 'text-emerald-400' : 'text-gray-300'
                  }`}
                  onClick={() => selectOffset(opt.offset)}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
    </header>
  )
}
