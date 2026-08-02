import { BasePrimitive, type CoordConverter, drawCanvasLine } from './BasePrimitive'
import type { Drawing } from '../types'

export class TrendLinePrimitive extends BasePrimitive {
  constructor(drawing: Drawing) { super(drawing) }

  protected _draw(ctx: CanvasRenderingContext2D, conv: CoordConverter): void {
    const [p1, p2] = this._drawing.points
    if (!p1 || !p2) return
    const x1 = conv.timeToX(p1.time)
    const y1 = conv.priceToY(p1.price)
    const x2 = conv.timeToX(p2.time)
    const y2 = conv.priceToY(p2.price)
    if (x1 === null || y1 === null || x2 === null || y2 === null) return
    drawCanvasLine(ctx, x1, y1, x2, y2, this._drawing.style)

    if (this._drawing.label) {
      const midX = (x1 + x2) / 2
      const midY = (y1 + y2) / 2
      ctx.save()
      ctx.font = `${(this._drawing.style.fontSize ?? 12)}px sans-serif`
      ctx.fillStyle = this._drawing.style.color
      ctx.textAlign = 'center'
      ctx.textBaseline = 'bottom'
      ctx.fillText(this._drawing.label, midX, midY - 12)
      ctx.restore()
    }
  }
}
