import { BasePrimitive, type CoordConverter, applyLineDash } from './BasePrimitive'
import type { Drawing } from '../types'

const EXT_LEVELS = [0, 0.382, 0.618, 1, 1.272, 1.618, 2, 2.618]

export class FibExtensionPrimitive extends BasePrimitive {
  constructor(drawing: Drawing) { super(drawing) }

  protected _draw(ctx: CanvasRenderingContext2D, conv: CoordConverter): void {
    const [p1, p2, p3] = this._drawing.points
    if (!p1 || !p2 || !p3) return
    const x1 = conv.timeToX(p1.time)
    const x3 = conv.timeToX(p3.time)
    if (x1 === null || x3 === null) return
    const xMin = Math.min(x1, x3)
    const xMax = Math.max(x1, x3)

    const range = Math.abs(p2.price - p1.price)
    const dir = p2.price > p1.price ? 1 : -1

    for (const level of EXT_LEVELS) {
      const price = p3.price + dir * range * level
      const y = conv.priceToY(price)
      if (y === null) continue
      ctx.save()
      ctx.strokeStyle = this._drawing.style.color
      ctx.lineWidth = 1
      applyLineDash(ctx, this._drawing.style.lineStyle)
      ctx.beginPath()
      ctx.moveTo(xMin, y)
      ctx.lineTo(xMax, y)
      ctx.stroke()
      ctx.font = '10px monospace'
      ctx.fillStyle = this._drawing.style.color
      ctx.fillText(`${(level * 100).toFixed(1)}%  ${price.toFixed(5)}`, xMax + 4, y + 3)
      ctx.restore()
    }
  }
}
