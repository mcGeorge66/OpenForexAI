import { BasePrimitive, type CoordConverter, drawCanvasLine, drawHandle } from './BasePrimitive'
import type { Drawing } from '../types'

export class ElliottWavePrimitive extends BasePrimitive {
  constructor(drawing: Drawing) { super(drawing) }

  protected _draw(ctx: CanvasRenderingContext2D, conv: CoordConverter): void {
    const pts = this._drawing.points
    if (pts.length < 2) return
    const labels = this._drawing.elliottLabels ?? ['1', '2', '3', '4', '5']

    // Connect points with lines
    for (let i = 0; i < pts.length - 1; i++) {
      const x1 = conv.timeToX(pts[i].time)
      const y1 = conv.priceToY(pts[i].price)
      const x2 = conv.timeToX(pts[i + 1].time)
      const y2 = conv.priceToY(pts[i + 1].price)
      if (x1 === null || y1 === null || x2 === null || y2 === null) continue
      drawCanvasLine(ctx, x1, y1, x2, y2, this._drawing.style)
    }

    // Draw labels and point markers
    for (let i = 0; i < pts.length; i++) {
      const x = conv.timeToX(pts[i].time)
      const y = conv.priceToY(pts[i].price)
      if (x === null || y === null) continue

      drawHandle(ctx, x, y, this._drawing.style.color)

      const label = labels[i] ?? String(i + 1)
      ctx.save()
      ctx.font = 'bold 11px monospace'
      ctx.fillStyle = '#fff'
      ctx.strokeStyle = this._drawing.style.color
      ctx.lineWidth = 3
      ctx.strokeText(label, x + 5, y - 5)
      ctx.fillText(label, x + 5, y - 5)
      ctx.restore()
    }
  }

  protected _drawHandles(_ctx: CanvasRenderingContext2D, _conv: CoordConverter): void {
    // Handles already drawn inline in _draw
  }
}
