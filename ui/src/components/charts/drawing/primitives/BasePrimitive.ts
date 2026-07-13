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
import type { BitmapCoordinatesRenderingScope } from 'fancy-canvas'
import { LineStyle } from 'lightweight-charts'
import type { Drawing, DrawingStyle } from '../types'

export interface CoordConverter {
  priceToY: (price: number) => number | null
  timeToX: (time: UTCTimestamp) => number | null
  width: number
  height: number
}

export function drawCanvasLine(
  ctx: CanvasRenderingContext2D,
  x1: number,
  y1: number,
  x2: number,
  y2: number,
  style: DrawingStyle,
): void {
  ctx.save()
  ctx.strokeStyle = style.color
  ctx.lineWidth = style.lineWidth
  applyLineDash(ctx, style.lineStyle)
  ctx.beginPath()
  ctx.moveTo(x1, y1)
  ctx.lineTo(x2, y2)
  ctx.stroke()
  ctx.restore()
}

export function applyLineDash(ctx: CanvasRenderingContext2D, ls: number): void {
  switch (ls) {
    case LineStyle.Dashed:      ctx.setLineDash([6, 4]);  break
    case LineStyle.LargeDashed: ctx.setLineDash([12, 6]); break
    case LineStyle.SparseDotted:ctx.setLineDash([2, 6]);  break
    case LineStyle.Dotted:      ctx.setLineDash([2, 3]);  break
    default:                    ctx.setLineDash([])
  }
}

export function drawHandle(ctx: CanvasRenderingContext2D, x: number, y: number, color: string): void {
  ctx.save()
  ctx.fillStyle = color
  ctx.strokeStyle = '#fff'
  ctx.lineWidth = 1
  ctx.beginPath()
  ctx.arc(x, y, 4, 0, Math.PI * 2)
  ctx.fill()
  ctx.stroke()
  ctx.restore()
}

// Pane view that wraps a draw callback
class SimplePaneView implements IPrimitivePaneView {
  private _draw: (scope: BitmapCoordinatesRenderingScope) => void

  constructor(draw: (scope: BitmapCoordinatesRenderingScope) => void) {
    this._draw = draw
  }

  renderer(): IPrimitivePaneRenderer {
    const draw = this._draw
    return {
      draw(target: CanvasRenderingTarget2D) {
        target.useBitmapCoordinateSpace(scope => draw(scope))
      },
    }
  }
}

// Abstract base for all drawing primitives
export abstract class BasePrimitive implements ISeriesPrimitive {
  protected _drawing: Drawing
  protected _series: ISeriesApi<'Candlestick'> | null = null
  protected _chart: IChartApi | null = null

  constructor(drawing: Drawing) {
    this._drawing = { ...drawing }
  }

  attached(params: SeriesAttachedParameter): void {
    // Cast: we know this primitive is attached to the candlestick series
    this._series = params.series as unknown as ISeriesApi<'Candlestick'>
    this._chart = params.chart as unknown as IChartApi
  }

  detached(): void {
    this._series = null
    this._chart = null
  }

  updateData(drawing: Drawing): void {
    this._drawing = { ...drawing }
  }

  protected _getConverter(): CoordConverter {
    const series = this._series
    const chart = this._chart
    return {
      priceToY: (price: number) => {
        if (!series) return null
        return series.priceToCoordinate(price) ?? null
      },
      timeToX: (time: UTCTimestamp) => {
        if (!chart) return null
        return chart.timeScale().timeToCoordinate(time) ?? null
      },
      width: 0,
      height: 0,
    }
  }

  paneViews(): readonly IPrimitivePaneView[] {
    return [
      new SimplePaneView((scope: BitmapCoordinatesRenderingScope) => {
        if (!this._drawing.visible) return
        const { width, height } = scope.bitmapSize
        const ratio = scope.horizontalPixelRatio

        const base = this._getConverter()
        const conv: CoordConverter = {
          priceToY: (price) => {
            const y = base.priceToY(price)
            return y === null ? null : y * ratio
          },
          timeToX: (time) => {
            const x = base.timeToX(time)
            return x === null ? null : x * ratio
          },
          width,
          height,
        }
        this._draw(scope.context, conv)
        if (this._drawing.selected) {
          this._drawHandles(scope.context, conv)
        }
      }),
    ]
  }

  protected abstract _draw(ctx: CanvasRenderingContext2D, conv: CoordConverter): void

  protected _drawHandles(ctx: CanvasRenderingContext2D, conv: CoordConverter): void {
    for (const pt of this._drawing.points) {
      const x = conv.timeToX(pt.time)
      const y = conv.priceToY(pt.price)
      if (x !== null && y !== null) {
        drawHandle(ctx, x, y, this._drawing.style.color)
      }
    }
  }
}
