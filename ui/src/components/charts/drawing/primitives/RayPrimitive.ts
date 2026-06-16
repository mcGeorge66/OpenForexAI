import { BasePrimitive, type CoordConverter, drawCanvasLine } from './BasePrimitive'
import type { Drawing } from '../types'

// Horizontal ray: extends right from the anchor point
export class RayPrimitive extends BasePrimitive {
  constructor(drawing: Drawing) { super(drawing) }

  protected _draw(ctx: CanvasRenderingContext2D, conv: CoordConverter): void {
    const p = this._drawing.points[0]
    if (!p) return
    const x = conv.timeToX(p.time)
    const y = conv.priceToY(p.price)
    if (x === null || y === null) return
    drawCanvasLine(ctx, x, y, conv.width, y, this._drawing.style)
  }
}
