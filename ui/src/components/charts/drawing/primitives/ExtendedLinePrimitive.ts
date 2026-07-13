import { BasePrimitive, type CoordConverter, drawCanvasLine } from './BasePrimitive'
import type { Drawing } from '../types'

// Extended line: passes through two anchor points and extends infinitely in both directions
export class ExtendedLinePrimitive extends BasePrimitive {
  constructor(drawing: Drawing) { super(drawing) }

  protected _draw(ctx: CanvasRenderingContext2D, conv: CoordConverter): void {
    const [p1, p2] = this._drawing.points
    if (!p1 || !p2) return
    const x1 = conv.timeToX(p1.time)
    const y1 = conv.priceToY(p1.price)
    const x2 = conv.timeToX(p2.time)
    const y2 = conv.priceToY(p2.price)
    if (x1 === null || y1 === null || x2 === null || y2 === null) return

    if (Math.abs(x2 - x1) < 0.001) {
      // Vertical degenerate case — draw a vertical line
      drawCanvasLine(ctx, x1, 0, x1, conv.height, this._drawing.style)
      return
    }

    const slope = (y2 - y1) / (x2 - x1)
    const yLeft  = y1 + slope * (0 - x1)
    const yRight = y1 + slope * (conv.width - x1)
    drawCanvasLine(ctx, 0, yLeft, conv.width, yRight, this._drawing.style)
  }
}
