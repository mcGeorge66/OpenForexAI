import { BasePrimitive, type CoordConverter, drawCanvasLine } from './BasePrimitive'
import type { Drawing } from '../types'

// Parallel Channel: p1+p2 define the main line, p3 defines the offset (parallel line)
export class ChannelPrimitive extends BasePrimitive {
  constructor(drawing: Drawing) { super(drawing) }

  protected _draw(ctx: CanvasRenderingContext2D, conv: CoordConverter): void {
    const [p1, p2, p3] = this._drawing.points
    if (!p1 || !p2) return
    const x1 = conv.timeToX(p1.time)
    const y1 = conv.priceToY(p1.price)
    const x2 = conv.timeToX(p2.time)
    const y2 = conv.priceToY(p2.price)
    if (x1 === null || y1 === null || x2 === null || y2 === null) return

    // Main line
    drawCanvasLine(ctx, x1, y1, x2, y2, this._drawing.style)

    if (!p3) return
    const x3 = conv.timeToX(p3.time)
    const y3 = conv.priceToY(p3.price)
    if (x3 === null || y3 === null) return
    // y-value of the main line at x3 — parallel line must pass through p3
    const yMainAtX3 = x2 === x1 ? y1 : y1 + (y2 - y1) * (x3 - x1) / (x2 - x1)
    const dy = y3 - yMainAtX3

    // Parallel line shifted by dy
    drawCanvasLine(ctx, x1, y1 + dy, x2, y2 + dy, this._drawing.style)

    // Shaded fill between lines
    const fill = this._drawing.style.fillColor ?? this._drawing.style.color
    const alpha = this._drawing.style.fillOpacity ?? 0.1
    ctx.save()
    ctx.globalAlpha = alpha
    ctx.fillStyle = fill
    ctx.beginPath()
    ctx.moveTo(x1, y1)
    ctx.lineTo(x2, y2)
    ctx.lineTo(x2, y2 + dy)
    ctx.lineTo(x1, y1 + dy)
    ctx.closePath()
    ctx.fill()
    ctx.restore()
  }
}
