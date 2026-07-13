import { BasePrimitive, type CoordConverter, applyLineDash } from './BasePrimitive'
import type { Drawing } from '../types'

export class MeasureLinePrimitive extends BasePrimitive {
  constructor(drawing: Drawing) { super(drawing) }

  protected _draw(ctx: CanvasRenderingContext2D, conv: CoordConverter): void {
    const [p1, p2] = this._drawing.points
    if (!p1 || !p2) return
    const x1 = conv.timeToX(p1.time)
    const y1 = conv.priceToY(p1.price)
    const x2 = conv.timeToX(p2.time)
    const y2 = conv.priceToY(p2.price)
    if (x1 === null || y1 === null || x2 === null || y2 === null) return

    const { color, lineWidth } = this._drawing.style

    // Semi-transparent fill
    ctx.save()
    ctx.fillStyle = color
    ctx.globalAlpha = 0.12
    ctx.fillRect(Math.min(x1, x2), Math.min(y1, y2), Math.abs(x2 - x1), Math.abs(y2 - y1))
    ctx.globalAlpha = 1

    // Main line
    ctx.strokeStyle = color
    ctx.lineWidth = lineWidth
    applyLineDash(ctx, this._drawing.style.lineStyle)
    ctx.beginPath()
    ctx.moveTo(x1, y1)
    ctx.lineTo(x2, y2)
    ctx.stroke()

    // Tick marks at start and end
    const tick = 10
    ctx.setLineDash([])
    ctx.lineWidth = lineWidth
    ctx.beginPath()
    ctx.moveTo(x1, y1 - tick); ctx.lineTo(x1, y1 + tick)
    ctx.moveTo(x2, y2 - tick); ctx.lineTo(x2, y2 + tick)
    ctx.stroke()
    ctx.restore()

    // ── Stats ─────────────────────────────────────────────────────────────────
    const pipSize = Math.max(p1.price, p2.price) > 20 ? 0.01 : 0.0001
    const pips = (p2.price - p1.price) / pipSize

    // Candle count via series data
    let candleCount = 0
    if (this._series) {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const data = (this._series as any).data() as Array<{ time: number }>
      if (Array.isArray(data) && data.length > 0) {
        const tMin = Math.min(p1.time, p2.time)
        const tMax = Math.max(p1.time, p2.time)
        candleCount = data.filter(d => d.time >= tMin && d.time <= tMax).length - 1
      }
    }

    const sign = pips >= 0 ? '+' : ''
    const label = `${candleCount}c   ${sign}${pips.toFixed(1)}p`

    const mx = (x1 + x2) / 2
    const fontSize = 18
    const position = (this._drawing.label ?? 'top') as 'top' | 'middle' | 'bottom'
    const topY = Math.min(y1, y2)
    const botY = Math.max(y1, y2)
    const midY = (y1 + y2) / 2
    ctx.save()
    ctx.font = `bold ${fontSize}px monospace`
    const tw = ctx.measureText(label).width
    const pad = 8
    const bw = tw + pad * 2
    const bh = fontSize + pad
    const bx = mx - bw / 2
    const by = position === 'top'    ? topY - bh - 6
             : position === 'bottom' ? botY + 6
             : midY - bh / 2

    // Label background
    ctx.fillStyle = 'rgba(17,24,39,0.88)'
    ctx.strokeStyle = color
    ctx.lineWidth = 1.5
    ctx.setLineDash([])
    ctx.beginPath()
    const r = 4
    ctx.moveTo(bx + r, by)
    ctx.lineTo(bx + bw - r, by)
    ctx.arcTo(bx + bw, by, bx + bw, by + r, r)
    ctx.lineTo(bx + bw, by + bh - r)
    ctx.arcTo(bx + bw, by + bh, bx + bw - r, by + bh, r)
    ctx.lineTo(bx + r, by + bh)
    ctx.arcTo(bx, by + bh, bx, by + bh - r, r)
    ctx.lineTo(bx, by + r)
    ctx.arcTo(bx, by, bx + r, by, r)
    ctx.closePath()
    ctx.fill()
    ctx.stroke()

    // Label text
    ctx.fillStyle = color
    ctx.textAlign = 'center'
    ctx.textBaseline = 'middle'
    ctx.fillText(label, mx, by + bh / 2)
    ctx.restore()
  }
}
