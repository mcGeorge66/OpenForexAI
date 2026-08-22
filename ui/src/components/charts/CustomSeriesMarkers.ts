/**
 * CustomSeriesMarkers — drop-in replacement for lightweight-charts' native
 * `createSeriesMarkers()` primitive, built because the native one has two
 * hard limits with no public option to change them:
 *
 * 1. Text is drawn with a single `ctx.fillText(text, x, y)` call — a `\n` in
 *    the string is not interpreted as a line break, it just renders as an
 *    unsupported glyph. There is no multi-line support at all.
 * 2. The shape-to-text gap (`shapeMargin`) is computed internally from bar
 *    spacing and a hardcoded constant — `SeriesMarkersOptions` only exposes
 *    `autoScale`/`zOrder`, nothing about spacing.
 *
 * This primitive takes the same `ForexChartMarker[]` shape ForexChart.tsx
 * already used for the native primitive, so swapping it in required no
 * change to any caller (PromptWorkbench, ChartAnalysis, etc.) — only
 * `marker.text` containing an actual `\n` behaves differently now: it draws
 * as two lines instead of a single garbled one. Spacing constants below are
 * real, editable numbers (there was nothing to "turn on" for this in the
 * native primitive — building this is what makes spacing configurable at
 * all).
 */
import type {
  IChartApi,
  ISeriesApi,
  ISeriesPrimitive,
  IPrimitivePaneView,
  IPrimitivePaneRenderer,
  SeriesAttachedParameter,
  UTCTimestamp,
} from 'lightweight-charts'
import { CanvasRenderingTarget2D } from 'fancy-canvas'
import type { CandleBar } from '@/api/client'

export interface CustomSeriesMarker {
  time: UTCTimestamp
  position: 'aboveBar' | 'belowBar' | 'inBar'
  shape: 'arrowUp' | 'arrowDown' | 'circle' | 'square'
  color: string
  /** A literal '\n' splits this into two drawn lines instead of one. */
  text?: string
  /** Bigger/bold text with a dark outline, for markers that must stand out (e.g. trade start/end) — default styling otherwise. */
  emphasis?: boolean
}

export interface CustomSeriesMarkersSpacing {
  /** Shape radius/half-size in CSS px. */
  shapeSize: number
  /** Gap between the shape's edge and the first line of text, in CSS px. */
  shapeTextGap: number
  /** Gap between the first and second text line, in CSS px (only matters for 2-line text). */
  lineGap: number
  /** Extra gap added per marker when multiple markers share the same time+position, so they stack instead of overlapping. */
  stackGap: number
}

const FONT = '10px sans-serif'
const LINE_HEIGHT = 11 // px, matches FONT's line box — used for stacking offset after text

export const DEFAULT_MARKER_SPACING: CustomSeriesMarkersSpacing = {
  shapeSize: 5,
  // At least 4 text-line-heights between the shape and the text, above or below
  // (doubled from the initial 2-line-height gap per user feedback).
  shapeTextGap: LINE_HEIGHT * 4,
  lineGap: 12,
  stackGap: 4,
}

export class CustomSeriesMarkers implements ISeriesPrimitive {
  private _markers: CustomSeriesMarker[] = []
  private _candlesByTime = new Map<number, CandleBar>()
  private _chart: IChartApi | null = null
  private _series: ISeriesApi<'Candlestick'> | null = null
  private _spacing: CustomSeriesMarkersSpacing

  constructor(spacing: Partial<CustomSeriesMarkersSpacing> = {}) {
    this._spacing = { ...DEFAULT_MARKER_SPACING, ...spacing }
  }

  setSpacing(spacing: Partial<CustomSeriesMarkersSpacing>): void {
    this._spacing = { ...this._spacing, ...spacing }
  }

  setMarkers(markers: CustomSeriesMarker[], candles: CandleBar[]): void {
    this._markers = markers
    this._candlesByTime.clear()
    for (const c of candles) {
      this._candlesByTime.set(Math.floor(new Date(c.timestamp).getTime() / 1000), c)
    }
  }

  attached(params: SeriesAttachedParameter): void {
    this._chart = params.chart as unknown as IChartApi
    this._series = params.series as unknown as ISeriesApi<'Candlestick'>
  }

  detached(): void {
    this._chart = null
    this._series = null
  }

  paneViews(): readonly IPrimitivePaneView[] {
    const markers = this._markers
    const candlesByTime = this._candlesByTime
    const chart = this._chart
    const series = this._series
    const spacing = this._spacing

    return [{
      renderer(): IPrimitivePaneRenderer {
        return {
          draw(target: CanvasRenderingTarget2D) {
            target.useBitmapCoordinateSpace(scope => {
              if (!chart || !series || markers.length === 0) return
              const { context: ctx, horizontalPixelRatio, verticalPixelRatio } = scope

              // Track how many markers have already been placed at the same
              // (time, position) so later ones stack further out instead of
              // drawing on top of each other — same idea as the native
              // primitive's per-bar offset accumulation, simplified.
              const stackIndex = new Map<string, number>()

              ctx.save()
              ctx.font = FONT
              ctx.textAlign = 'center'

              for (const marker of markers) {
                const x = chart.timeScale().timeToCoordinate(marker.time)
                if (x === null) continue
                const candle = candlesByTime.get(marker.time as unknown as number)
                if (!candle) continue

                const anchorPrice = marker.position === 'belowBar' ? candle.low : candle.high
                const anchorY = series.priceToCoordinate(anchorPrice)
                if (anchorY === null) continue

                const stackKey = `${marker.time}:${marker.position}`
                const stack = stackIndex.get(stackKey) ?? 0
                stackIndex.set(stackKey, stack + 1)

                const lines = (marker.text ?? '').split('\n').filter(Boolean)
                const textBlockHeight = lines.length * LINE_HEIGHT + Math.max(0, lines.length - 1) * (spacing.lineGap - LINE_HEIGHT)
                const extent = spacing.shapeSize * 2 + spacing.shapeTextGap + textBlockHeight + stack * (spacing.shapeSize * 2 + spacing.stackGap)

                const goingUp = marker.position === 'belowBar' // shape+text extend downward from the low
                const shapeCenterY = goingUp
                  ? anchorY * verticalPixelRatio + (spacing.shapeSize + stack * (spacing.shapeSize * 2 + spacing.stackGap)) * verticalPixelRatio
                  : anchorY * verticalPixelRatio - (spacing.shapeSize + stack * (spacing.shapeSize * 2 + spacing.stackGap)) * verticalPixelRatio

                const xBmp = x * horizontalPixelRatio
                const sizeBmp = spacing.shapeSize * Math.min(horizontalPixelRatio, verticalPixelRatio)

                ctx.fillStyle = marker.color
                drawShape(ctx, marker.shape, xBmp, shapeCenterY, sizeBmp)

                if (lines.length > 0) {
                  const textStartY = goingUp
                    ? shapeCenterY + (spacing.shapeSize + spacing.shapeTextGap) * verticalPixelRatio
                    : shapeCenterY - (spacing.shapeSize + spacing.shapeTextGap) * verticalPixelRatio - (lines.length - 1) * spacing.lineGap * verticalPixelRatio
                  const scale = Math.min(horizontalPixelRatio, verticalPixelRatio)
                  const fontSize = marker.emphasis ? 12 : 10
                  ctx.font = `${marker.emphasis ? 'bold ' : ''}${fontSize * scale}px sans-serif`
                  ctx.textBaseline = 'middle'
                  ctx.lineJoin = 'round'
                  for (let i = 0; i < lines.length; i++) {
                    const ty = textStartY + i * spacing.lineGap * verticalPixelRatio
                    if (marker.emphasis) {
                      // Dark outline behind the fill so the label reads against any
                      // candle color behind it, instead of just the flat marker color
                      // (which could match/blend into similarly-colored candles).
                      ctx.strokeStyle = 'rgba(0, 0, 0, 0.9)'
                      ctx.lineWidth = 3 * scale
                      ctx.strokeText(lines[i], xBmp, ty)
                    }
                    ctx.fillStyle = marker.color
                    ctx.fillText(lines[i], xBmp, ty)
                  }
                }
                void extent // reserved for a future autoscaleInfo() that expands the price range to fit stacked text; not needed yet since markers already sit within the candle range in practice
              }

              ctx.restore()
            })
          },
        }
      },
    }]
  }
}

function drawShape(
  ctx: CanvasRenderingContext2D,
  shape: CustomSeriesMarker['shape'],
  x: number,
  y: number,
  size: number,
): void {
  ctx.beginPath()
  if (shape === 'circle') {
    ctx.arc(x, y, size, 0, Math.PI * 2)
    ctx.fill()
    return
  }
  if (shape === 'square') {
    ctx.fillRect(x - size, y - size, size * 2, size * 2)
    return
  }
  const dir = shape === 'arrowDown' ? 1 : -1
  ctx.moveTo(x, y + dir * size)
  ctx.lineTo(x - size, y - dir * size)
  ctx.lineTo(x + size, y - dir * size)
  ctx.closePath()
  ctx.fill()
}
