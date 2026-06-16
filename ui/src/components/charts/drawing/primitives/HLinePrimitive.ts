import { BasePrimitive, type CoordConverter, drawCanvasLine } from './BasePrimitive'
import type { Drawing } from '../types'

export class HLinePrimitive extends BasePrimitive {
  constructor(drawing: Drawing) { super(drawing) }

  protected _draw(ctx: CanvasRenderingContext2D, conv: CoordConverter): void {
    const p = this._drawing.points[0]
    if (!p) return
    const y = conv.priceToY(p.price)
    if (y === null) return
    drawCanvasLine(ctx, 0, y, conv.width, y, this._drawing.style)
    // Price label
    ctx.save()
    ctx.font = '13px monospace'
    ctx.fillStyle = this._drawing.style.color
    ctx.fillText(p.price.toFixed(5), 4, y - 3)
    ctx.restore()
  }
}
