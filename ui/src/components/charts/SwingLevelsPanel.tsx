/**
 * SwingLevelsPanel — shared swing-high/low control panel.
 *
 * Extracted from ChartAnalysis.tsx so the Prompt Workbench's Analyse tab uses
 * the same panel instead of a second, drifting copy (same pattern as
 * IndicatorsPanel). Purely presentational — state and the actual
 * get_swing_levels fetch stay in the consuming view, same convention as
 * IndicatorsPanel/addIndicator.
 */
import { LineStyle } from 'lightweight-charts'
import { TF_MINUTES } from '@/utils/indicators'
import type { ForexChartPriceLine } from './ForexChart'

export type SwingLevel = { price: number; timestamp: string; distance: number }
export type SwingResult = { highs: SwingLevel[]; lows: SwingLevel[]; confluence: SwingLevel[] }

export function SwingLevelsPanel({
  enabled,
  onToggle,
  timeframe,
  onTimeframeChange,
  count,
  onCountChange,
  atrPeriod,
  onAtrPeriodChange,
  minGapAtr,
  onMinGapAtrChange,
  lineWidth,
  onLineWidthChange,
  lineStyle,
  onLineStyleChange,
  priceSource,
  onPriceSourceChange,
  visibleOnly,
  onVisibleOnlyChange,
  sortBy,
  onSortByChange,
  loading,
  onReload,
  lines,
}: {
  enabled: boolean
  onToggle: () => void
  timeframe: string
  onTimeframeChange: (tf: string) => void
  count: number
  onCountChange: (n: number) => void
  atrPeriod: number
  onAtrPeriodChange: (n: number) => void
  minGapAtr: number
  onMinGapAtrChange: (n: number) => void
  lineWidth: number
  onLineWidthChange: (w: number) => void
  lineStyle: LineStyle
  onLineStyleChange: (s: LineStyle) => void
  priceSource: 'HL' | 'OC'
  onPriceSourceChange: (s: 'HL' | 'OC') => void
  // Omit both when the consumer always anchors to the visible window (no "All"
  // concept) — e.g. the Prompt Workbench, where the loaded chart must stay the
  // single source of truth and there's no meaningful "ignore what's visible" mode.
  visibleOnly?: boolean
  onVisibleOnlyChange?: (v: boolean) => void
  sortBy: 'nearest' | 'prominent'
  onSortByChange: (s: 'nearest' | 'prominent') => void
  loading: boolean
  onReload: () => void
  lines: ForexChartPriceLine[]
}) {
  return (
    <div>
      <div className="flex items-center gap-2 mb-2">
        <label className="flex items-center gap-1.5 cursor-pointer">
          <input
            type="checkbox"
            checked={enabled}
            onChange={onToggle}
            className="accent-emerald-500"
          />
          <span className="font-semibold text-gray-300 text-xs uppercase tracking-wide">Swing Levels</span>
        </label>
        {enabled && loading && <span className="text-white text-xs">Loading…</span>}
      </div>
      {enabled && (
        <div className="space-y-2">
          {/* Row 1: TF, Count, ATR, Gap */}
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-gray-400">TF</span>
            <select
              value={timeframe}
              onChange={e => onTimeframeChange(e.target.value)}
              className="bg-gray-800 border border-gray-700 rounded px-1 text-gray-200"
            >
              {Object.keys(TF_MINUTES).map(tf => (
                <option key={tf} value={tf}>{tf}</option>
              ))}
            </select>
            <span className="text-gray-400">Count</span>
            <input
              type="number" min={1} max={20} value={count}
              onChange={e => onCountChange(Number(e.target.value))}
              className="w-10 bg-gray-800 border border-gray-700 rounded px-1 text-gray-200"
            />
            <span className="text-gray-400">ATR</span>
            <input
              type="number" min={1} max={200} value={atrPeriod}
              onChange={e => onAtrPeriodChange(Math.max(1, Math.min(200, Number(e.target.value))))}
              className="w-12 bg-gray-800 border border-gray-700 rounded px-1 text-gray-200"
              title="ATR period for cluster gap"
            />
            <span className="text-gray-400">Gap</span>
            <input
              type="number" min={0} max={5} step={0.1} value={minGapAtr}
              onChange={e => onMinGapAtrChange(Math.max(0, Math.min(5, Number(e.target.value))))}
              className="w-12 bg-gray-800 border border-gray-700 rounded px-1 text-gray-200"
              title="Min gap as ATR multiple (0 = no clustering)"
            />
          </div>
          {/* Row 2: Next/Prominent, Visible/All, HL/OC */}
          <div className="flex items-center gap-2 flex-wrap">
            <div className="flex rounded border border-gray-700 overflow-hidden text-xs">
              {(['nearest', 'prominent'] as const).map(s => (
                <button key={s} onClick={() => onSortByChange(s)}
                  className={`px-2 py-0.5 ${sortBy === s ? 'bg-emerald-600 text-white' : 'bg-gray-800 text-gray-400 hover:text-white'}`}
                  title={s === 'nearest' ? 'Closest to current price' : 'Most visually prominent'}
                >
                  {s === 'nearest' ? 'Next' : 'Prominent'}
                </button>
              ))}
            </div>
            {onVisibleOnlyChange && (
              <div className="flex rounded border border-gray-700 overflow-hidden text-xs">
                {([['Visible', true], ['All', false]] as const).map(([lbl, val]) => (
                  <button key={lbl} onClick={() => onVisibleOnlyChange(val)}
                    className={`px-2 py-0.5 ${visibleOnly === val ? 'bg-emerald-600 text-white' : 'bg-gray-800 text-gray-400 hover:text-white'}`}
                  >
                    {lbl}
                  </button>
                ))}
              </div>
            )}
            <div className="flex rounded border border-gray-700 overflow-hidden text-xs">
              {(['HL', 'OC'] as const).map(src => (
                <button key={src} onClick={() => onPriceSourceChange(src)}
                  className={`px-2 py-0.5 ${priceSource === src ? 'bg-emerald-600 text-white' : 'bg-gray-800 text-gray-400 hover:text-white'}`}
                >
                  {src}
                </button>
              ))}
            </div>
          </div>
          {/* Row 3: Width, Style, Reload */}
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-gray-400">Width</span>
            <input
              type="number" min={1} max={5} value={lineWidth}
              onChange={e => onLineWidthChange(Math.max(1, Math.min(5, Number(e.target.value))))}
              className="w-10 bg-gray-800 border border-gray-700 rounded px-1 text-gray-200"
            />
            <span className="text-gray-400">Style</span>
            <select
              value={lineStyle}
              onChange={e => onLineStyleChange(Number(e.target.value) as LineStyle)}
              className="bg-gray-800 border border-gray-700 rounded px-1 text-gray-200"
            >
              <option value={LineStyle.Solid}>Solid</option>
              <option value={LineStyle.Dashed}>Dashed</option>
              <option value={LineStyle.LargeDashed}>Large Dashed</option>
              <option value={LineStyle.Dotted}>Dotted</option>
              <option value={LineStyle.SparseDotted}>Sparse Dotted</option>
            </select>
            <button
              onClick={onReload}
              className="px-2 py-0.5 rounded border border-gray-700 bg-gray-800 text-gray-300 hover:text-white text-xs"
            >
              Reload
            </button>
          </div>
          {lines.length > 0 && (
            <div className="space-y-0.5 max-h-24 overflow-y-auto">
              {lines.map((l, i) => (
                <div key={i} className="flex items-center gap-1.5">
                  <div className="w-2 h-2 rounded-full flex-shrink-0" style={{ backgroundColor: l.color }} />
                  <span className="text-gray-400">{l.title}</span>
                </div>
              ))}
            </div>
          )}
          {lines.length === 0 && !loading && (
            <p className="text-white text-xs">No swing levels found.</p>
          )}
        </div>
      )}
    </div>
  )
}
