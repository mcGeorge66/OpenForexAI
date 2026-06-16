import { BasePrimitive, type CoordConverter, drawCanvasLine } from './BasePrimitive'
import type { Drawing } from '../types'

// Andrews' Pitchfork: p0 = handle/pivot, p1 = upper fork, p2 = lower fork
export class PitchforkPrimitive extends BasePrimitive {
  constructor(drawing: Drawing) { super(drawing) }

  protected _draw(ctx: CanvasRenderingContext2D, conv: CoordConverter): void {
    const [p0, p1, p2] = this._drawing.points
    if (!p0 || !p1 || !p2) return
    const x0 = conv.timeToX(p0.time)
    const y0 = conv.priceToY(p0.price)
    const x1 = conv.timeToX(p1.time)
    const y1 = conv.priceToY(p1.price)
    const x2 = conv.timeToX(p2.time)
    const y2 = conv.priceToY(p2.price)
    if (x0 === null || y0 === null || x1 === null || y1 === null || x2 === null || y2 === null) return

    // Midpoint of p1–p2
    const mx = (x1 + x2) / 2
    const my = (y1 + y2) / 2

    // Direction vector of median line
    const dx = mx - x0
    const dy = my - y0

    // Extend median line to canvas edge
    const scale = 10
    const xEnd = x0 + dx * scale
    const yEnd = y0 + dy * scale

    drawCanvasLine(ctx, x0, y0, xEnd, yEnd, this._drawing.style)

    // Upper fork: parallel to median through p1
    drawCanvasLine(ctx, x1, y1, x1 + dx * scale, y1 + dy * scale, this._drawing.style)
    // Lower fork: parallel to median through p2
    drawCanvasLine(ctx, x2, y2, x2 + dx * scale, y2 + dy * scale, this._drawing.style)

    // Handle bar connecting p1 and p2
    drawCanvasLine(ctx, x1, y1, x2, y2, { ...this._drawing.style, lineWidth: 1 })
  }
}
