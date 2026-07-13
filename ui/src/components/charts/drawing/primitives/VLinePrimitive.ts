import { BasePrimitive, type CoordConverter, drawCanvasLine } from './BasePrimitive'
import type { Drawing } from '../types'

export class VLinePrimitive extends BasePrimitive {
  constructor(drawing: Drawing) { super(drawing) }

  protected _draw(ctx: CanvasRenderingContext2D, conv: CoordConverter): void {
    const p = this._drawing.points[0]
    if (!p) return
    const x = conv.timeToX(p.time)
    if (x === null) return
    drawCanvasLine(ctx, x, 0, x, conv.height, this._drawing.style)
  }
}
