import { BasePrimitive, type CoordConverter, drawCanvasLine } from './BasePrimitive'
import type { Drawing } from '../types'

const FAN_LEVELS = [0.382, 0.5, 0.618]
const FAN_COLORS = ['#3b82f6', '#22c55e', '#8b5cf6']

export class FibFanPrimitive extends BasePrimitive {
  constructor(drawing: Drawing) { super(drawing) }

  protected _draw(ctx: CanvasRenderingContext2D, conv: CoordConverter): void {
    const [p1, p2] = this._drawing.points
    if (!p1 || !p2) return
    const x1 = conv.timeToX(p1.time)
    const y1 = conv.priceToY(p1.price)
    const x2 = conv.timeToX(p2.time)
    const y2 = conv.priceToY(p2.price)
    if (x1 === null || y1 === null || x2 === null || y2 === null) return

    const priceRange = p2.price - p1.price
    const xRange = x2 - x1

    for (let i = 0; i < FAN_LEVELS.length; i++) {
      const level = FAN_LEVELS[i]
      const targetPrice = p1.price + priceRange * level
      const ty = conv.priceToY(targetPrice)
      if (ty === null) continue

      const style = { ...this._drawing.style, color: FAN_COLORS[i] ?? this._drawing.style.color }
      // Extend fan line to right edge of visible area
      const slope = (ty - y1) / (xRange || 1)
      const xEnd = conv.width
      const yEnd = y1 + slope * (xEnd - x1)
      drawCanvasLine(ctx, x1, y1, xEnd, yEnd, style)

      ctx.save()
      ctx.font = '10px monospace'
      ctx.fillStyle = style.color
      ctx.fillText(`${(level * 100).toFixed(1)}%`, xEnd - 40, yEnd - 3)
      ctx.restore()
    }
  }
}
