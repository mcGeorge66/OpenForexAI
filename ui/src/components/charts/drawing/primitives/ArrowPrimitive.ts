import { BasePrimitive, type CoordConverter } from './BasePrimitive'
import type { Drawing } from '../types'

const ARROW_SIZE = 14  // half-width of the triangle base in pixels
const OFFSET = 10     // distance from the price point to the arrow tip

export class ArrowUpPrimitive extends BasePrimitive {
  constructor(drawing: Drawing) { super(drawing) }

  protected _draw(ctx: CanvasRenderingContext2D, conv: CoordConverter): void {
    const p = this._drawing.points[0]
    if (!p) return
    const x = conv.timeToX(p.time)
    const y = conv.priceToY(p.price)
    if (x === null || y === null) return

    // Arrow tip points up towards the price, base is below
    const tipY = y + OFFSET
    const baseY = tipY + ARROW_SIZE * 1.5

    ctx.save()
    ctx.fillStyle = this._drawing.style.color
    ctx.strokeStyle = this._drawing.style.color
    ctx.lineWidth = 1
    ctx.beginPath()
    ctx.moveTo(x, tipY)
    ctx.lineTo(x - ARROW_SIZE, baseY)
    ctx.lineTo(x + ARROW_SIZE, baseY)
    ctx.closePath()
    ctx.fill()
    ctx.restore()
  }
}

export class ArrowDownPrimitive extends BasePrimitive {
  constructor(drawing: Drawing) { super(drawing) }

  protected _draw(ctx: CanvasRenderingContext2D, conv: CoordConverter): void {
    const p = this._drawing.points[0]
    if (!p) return
    const x = conv.timeToX(p.time)
    const y = conv.priceToY(p.price)
    if (x === null || y === null) return

    // Arrow tip points down towards the price, base is above
    const tipY = y - OFFSET
    const baseY = tipY - ARROW_SIZE * 1.5

    ctx.save()
    ctx.fillStyle = this._drawing.style.color
    ctx.strokeStyle = this._drawing.style.color
    ctx.lineWidth = 1
    ctx.beginPath()
    ctx.moveTo(x, tipY)
    ctx.lineTo(x - ARROW_SIZE, baseY)
    ctx.lineTo(x + ARROW_SIZE, baseY)
    ctx.closePath()
    ctx.fill()
    ctx.restore()
  }
}
