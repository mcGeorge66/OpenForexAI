/**
 * Indicator type/const definitions shared by IndicatorsPanel, Chart Analysis, and the
 * Prompt Workbench. Split out from IndicatorsPanel.tsx (a component-only file now) so
 * Fast Refresh can treat that file as component-only.
 */
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
