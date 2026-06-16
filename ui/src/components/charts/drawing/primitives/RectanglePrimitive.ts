import { BasePrimitive, type CoordConverter, applyLineDash } from './BasePrimitive'
import type { Drawing } from '../types'

export class RectanglePrimitive extends BasePrimitive {
  constructor(drawing: Drawing) { super(drawing) }

  protected _draw(ctx: CanvasRenderingContext2D, conv: CoordConverter): void {
    const [p1, p2] = this._drawing.points
    if (!p1 || !p2) return
    const x1 = conv.timeToX(p1.time)
    const y1 = conv.priceToY(p1.price)
    const x2 = conv.timeToX(p2.time)
    const y2 = conv.priceToY(p2.price)
    if (x1 === null || y1 === null || x2 === null || y2 === null) return

    const x = Math.min(x1, x2)
    const y = Math.min(y1, y2)
    const w = Math.abs(x2 - x1)
    const h = Math.abs(y2 - y1)

    // Fill
    const fill = this._drawing.style.fillColor ?? this._drawing.style.color
    const alpha = this._drawing.style.fillOpacity ?? 0.15
    ctx.save()
    ctx.globalAlpha = alpha
    ctx.fillStyle = fill
    ctx.fillRect(x, y, w, h)
    ctx.restore()

    // Border
    ctx.save()
    ctx.strokeStyle = this._drawing.style.color
    ctx.lineWidth = this._drawing.style.lineWidth
    applyLineDash(ctx, this._drawing.style.lineStyle)
    ctx.strokeRect(x, y, w, h)
    ctx.restore()
  }
}
