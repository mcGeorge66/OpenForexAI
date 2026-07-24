/**
 * IndicatorsPanel — shared "add / configure / remove" indicator instance list.
 *
 * Single source of truth for the indicator types and the panel UI, used by
 * both Chart Analysis and the Prompt Workbench so both look and behave
 * identically. Each view keeps its own `indicators` state and recompute
 * wiring (candle source differs per view) — only the types/consts/UI are
 * shared here.
 */
import { useState } from 'react'
import { Eye, EyeOff, Plus, Trash2 } from 'lucide-react'
import { LineStyle } from 'lightweight-charts'
import type { IndicatorValue } from '@/api/client'
import { TF_MINUTES } from '@/utils/indicators'

export const TIMEFRAMES = Object.keys(TF_MINUTES).filter(tf => tf !== 'M1')

export type IndicatorName = 'EMA' | 'SMA' | 'RSI' | 'ATR' | 'BB' | 'VWAP' | 'SLOPE_E' | 'SLOPE_S'

export interface IndicatorInstance {
  id: string
  name: IndicatorName
  period: number
  timeframe: string
  color: string
  lineStyle: LineStyle
  lineWidth: number
  visible: boolean
  data: IndicatorValue[]
  bbData?: { upper: IndicatorValue[]; middle: IndicatorValue[]; lower: IndicatorValue[] }
  smoothPeriod?: number   // EMA smoothing applied to output (for slope indicators)
}

export const INDICATOR_DEFS: Array<{ name: IndicatorName; label: string; isOscillator: boolean; defaultPeriod: number; hasBackend: boolean }> = [
  { name: 'EMA',       label: 'EMA',       isOscillator: false, defaultPeriod: 20, hasBackend: false },
  { name: 'SMA',       label: 'SMA',       isOscillator: false, defaultPeriod: 20, hasBackend: false },
  { name: 'RSI',       label: 'RSI',       isOscillator: true,  defaultPeriod: 14, hasBackend: false },
  { name: 'ATR',       label: 'ATR',       isOscillator: true,  defaultPeriod: 14, hasBackend: true  },
  { name: 'BB',        label: 'BB',        isOscillator: false, defaultPeriod: 20, hasBackend: true  },
  { name: 'VWAP',      label: 'VWAP',      isOscillator: false, defaultPeriod: 0,  hasBackend: true  },
  { name: 'SLOPE_E', label: 'SlopeE', isOscillator: true,  defaultPeriod: 20, hasBackend: true  },
  { name: 'SLOPE_S', label: 'SlopeS', isOscillator: true,  defaultPeriod: 20, hasBackend: true  },
]

export const LINE_STYLE_OPTIONS: Array<{ value: LineStyle; label: string }> = [
  { value: LineStyle.Solid,       label: 'Solid'       },
  { value: LineStyle.Dashed,      label: 'Dashed'      },
  { value: LineStyle.LargeDashed, label: 'LargeDashed' },
  { value: LineStyle.Dotted,      label: 'Dotted'      },
  { value: LineStyle.SparseDotted,label: 'SparseDotted'},
]

export const DEFAULT_COLORS = ['#10b981', '#3b82f6', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899', '#06b6d4', '#84cc16']

export function IndicatorsPanel({
  indicators,
  onAdd,
  onRemove,
  onUpdate,
}: {
  indicators: IndicatorInstance[]
  onAdd: (name: IndicatorName) => void
  onRemove: (id: string) => void
  onUpdate: (id: string, patch: Partial<IndicatorInstance>) => void
}) {
  const [expanded, setExpanded] = useState(true)

  return (
    <div>
      <div
        className="flex items-center justify-between cursor-pointer mb-2"
        onClick={() => setExpanded(v => !v)}
      >
        <span className="font-semibold text-gray-300 text-xs uppercase tracking-wide">Indicators</span>
        <span className="text-gray-500">{expanded ? '▾' : '▸'}</span>
      </div>
      {expanded && (
        <div className="space-y-2">
          {/* Add buttons */}
          <div className="flex flex-wrap gap-1">
            {INDICATOR_DEFS.map(def => (
              <button
                key={def.name}
                onClick={() => onAdd(def.name)}
                className="flex items-center gap-0.5 px-2 py-0.5 rounded border border-gray-700 bg-gray-800 text-gray-300 hover:text-white text-xs"
              >
                <Plus className="w-2.5 h-2.5" />{def.label}
              </button>
            ))}
          </div>
          {/* Instance list */}
          {indicators.length === 0 && <p className="text-white text-xs">No indicators added.</p>}
          {indicators.map(ind => (
            <div key={ind.id} className="flex items-center gap-1.5 bg-gray-900 rounded px-2 py-1.5 border border-gray-800">
              <button onClick={() => onUpdate(ind.id, { visible: !ind.visible })} className="text-gray-400 hover:text-white">
                {ind.visible ? <Eye className="w-3 h-3" /> : <EyeOff className="w-3 h-3 opacity-40" />}
              </button>
              <input
                type="color"
                value={ind.color}
                onChange={e => onUpdate(ind.id, { color: e.target.value })}
                className="w-5 h-5 cursor-pointer rounded border-0 bg-transparent"
              />
              <span className="text-gray-300 font-medium w-10 shrink-0">{ind.name}</span>
              <input
                type="number"
                min={ind.name === 'VWAP' ? 0 : 1}
                max={500}
                value={ind.period}
                onChange={e => onUpdate(ind.id, { period: Number(e.target.value) })}
                className="w-14 bg-gray-800 border border-gray-700 rounded px-1 text-gray-200"
                title={ind.name === 'VWAP' ? 'Period (0 = daily reset from 00:00 UTC)' : 'Period'}
              />
              <select
                value={ind.timeframe}
                onChange={e => onUpdate(ind.id, { timeframe: e.target.value })}
                className="bg-gray-800 border border-gray-700 rounded px-1 text-gray-200"
              >
                {TIMEFRAMES.map(tf => <option key={tf} value={tf}>{tf}</option>)}
              </select>
              <select
                value={ind.lineStyle}
                onChange={e => onUpdate(ind.id, { lineStyle: Number(e.target.value) as LineStyle })}
                className="bg-gray-800 border border-gray-700 rounded px-1 text-gray-200 hidden sm:block"
              >
                {LINE_STYLE_OPTIONS.map(opt => (
                  <option key={opt.value} value={opt.value}>{opt.label}</option>
                ))}
              </select>
              <input
                type="number"
                min={1}
                max={4}
                value={ind.lineWidth}
                onChange={e => onUpdate(ind.id, { lineWidth: Number(e.target.value) })}
                className="w-8 bg-gray-800 border border-gray-700 rounded px-1 text-gray-200"
                title="Line width"
              />
              {(['SLOPE_E', 'SLOPE_S'] as string[]).includes(ind.name) && (
                <input
                  type="number"
                  min={1}
                  max={20}
                  value={ind.smoothPeriod ?? 1}
                  onChange={e => onUpdate(ind.id, { smoothPeriod: Number(e.target.value) })}
                  className="w-14 bg-gray-800 border border-amber-700 rounded px-1 text-amber-200"
                  title="Smooth period (EMA applied to slope)"
                />
              )}
              <button onClick={() => onRemove(ind.id)} className="text-gray-500 hover:text-red-400 ml-auto">
                <Trash2 className="w-3 h-3" />
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
