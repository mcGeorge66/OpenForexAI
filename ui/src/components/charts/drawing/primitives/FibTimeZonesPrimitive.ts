import { BasePrimitive, type CoordConverter, applyLineDash } from './BasePrimitive'
import type { Drawing } from '../types'

// Fibonacci time interval sequence: 1, 1, 2, 3, 5, 8, 13, 21, 34, 55
const FIB_SEQ = [1, 1, 2, 3, 5, 8, 13, 21, 34, 55]

export class FibTimeZonesPrimitive extends BasePrimitive {
  constructor(drawing: Drawing) { super(drawing) }

  protected _draw(ctx: CanvasRenderingContext2D, conv: CoordConverter): void {
    const [p1, p2] = this._drawing.points
    if (!p1 || !p2) return
    const x1 = conv.timeToX(p1.time)
    const x2 = conv.timeToX(p2.time)
    if (x1 === null || x2 === null) return

    const unitPx = Math.abs(x2 - x1)
    const startX = Math.min(x1, x2)
    let cumulative = 0

    for (let i = 0; i < FIB_SEQ.length; i++) {
      cumulative += FIB_SEQ[i]
      const x = startX + cumulative * unitPx
      if (x > conv.width) break

      ctx.save()
      ctx.strokeStyle = this._drawing.style.color
      ctx.lineWidth = 1
      ctx.globalAlpha = 0.6
      applyLineDash(ctx, this._drawing.style.lineStyle)
      ctx.beginPath()
      ctx.moveTo(x, 0)
      ctx.lineTo(x, conv.height)
      ctx.stroke()
      ctx.font = '10px monospace'
      ctx.globalAlpha = 0.8
      ctx.fillStyle = this._drawing.style.color
      ctx.fillText(String(cumulative), x + 2, 14)
      ctx.restore()
    }
  }
}
