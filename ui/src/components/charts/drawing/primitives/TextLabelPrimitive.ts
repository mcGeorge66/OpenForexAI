import { BasePrimitive, type CoordConverter } from './BasePrimitive'
import type { Drawing } from '../types'

export class TextLabelPrimitive extends BasePrimitive {
  constructor(drawing: Drawing) { super(drawing) }

  protected _draw(ctx: CanvasRenderingContext2D, conv: CoordConverter): void {
    const p = this._drawing.points[0]
    if (!p) return
    const x = conv.timeToX(p.time)
    const y = conv.priceToY(p.price)
    if (x === null || y === null) return
    const lines = (this._drawing.label ?? 'Label').split('|')
    const fontSize = this._drawing.style.fontSize ?? 12
    const lineHeight = fontSize + 4
    const pad = 4
    ctx.save()
    ctx.font = `bold ${fontSize}px monospace`
    const maxWidth = lines.reduce((m, l) => Math.max(m, ctx.measureText(l).width), 0)
    const bw = maxWidth + pad * 2
    const bh = lines.length * lineHeight + pad
    ctx.globalAlpha = 0.7
    ctx.fillStyle = '#111827'
    ctx.fillRect(x - pad, y - bh + pad, bw, bh)
    ctx.globalAlpha = 1
    ctx.fillStyle = this._drawing.style.color
    lines.forEach((line, i) => {
      ctx.fillText(line, x, y - bh + pad + (i + 1) * lineHeight - 2)
    })
    ctx.restore()
  }
}
