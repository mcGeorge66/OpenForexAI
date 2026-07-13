import { BasePrimitive, type CoordConverter, applyLineDash } from './BasePrimitive'
import type { Drawing } from '../types'

const FIB_LEVELS = [0, 0.236, 0.382, 0.5, 0.618, 0.786, 1]
const FIB_COLORS = ['#ef4444', '#f97316', '#eab308', '#22c55e', '#3b82f6', '#8b5cf6', '#ef4444']

export class FibRetracementPrimitive extends BasePrimitive {
  constructor(drawing: Drawing) { super(drawing) }

  protected _draw(ctx: CanvasRenderingContext2D, conv: CoordConverter): void {
    const [p1, p2] = this._drawing.points
    if (!p1 || !p2) return
    const x1 = conv.timeToX(p1.time)
    const x2 = conv.timeToX(p2.time)
    const y1 = conv.priceToY(p1.price)
    const y2 = conv.priceToY(p2.price)
    if (x1 === null || x2 === null || y1 === null || y2 === null) return

    const xMin = Math.min(x1, x2)
    const xMax = Math.max(x1, x2)

    for (let i = 0; i < FIB_LEVELS.length; i++) {
      const level = FIB_LEVELS[i]
      const price = p1.price + (p2.price - p1.price) * level
      const y = conv.priceToY(price)
      if (y === null) continue
      const color = FIB_COLORS[i] ?? this._drawing.style.color

      ctx.save()
      ctx.strokeStyle = color
      ctx.lineWidth = 1
      applyLineDash(ctx, this._drawing.style.lineStyle)
      ctx.beginPath()
      ctx.moveTo(xMin, y)
      ctx.lineTo(xMax, y)
      ctx.stroke()
      ctx.font = '10px monospace'
      ctx.fillStyle = color
      ctx.fillText(`${(level * 100).toFixed(1)}%  ${price.toFixed(5)}`, xMax + 4, y + 3)
      ctx.restore()
    }

    // Trend line connecting p1 and p2
    ctx.save()
    ctx.strokeStyle = this._drawing.style.color
    ctx.lineWidth = this._drawing.style.lineWidth
    ctx.setLineDash([])
    ctx.beginPath()
    ctx.moveTo(x1, y1)
    ctx.lineTo(x2, y2)
    ctx.stroke()
    ctx.restore()
  }
}
