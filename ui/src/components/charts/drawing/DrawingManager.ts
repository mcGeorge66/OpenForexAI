import type { IChartApi, ISeriesApi } from 'lightweight-charts'
import type { Drawing } from './types'
import type { BasePrimitive } from './primitives/BasePrimitive'

import { HLinePrimitive } from './primitives/HLinePrimitive'
import { VLinePrimitive } from './primitives/VLinePrimitive'
import { RayPrimitive } from './primitives/RayPrimitive'
import { ExtendedLinePrimitive } from './primitives/ExtendedLinePrimitive'
import { TrendLinePrimitive } from './primitives/TrendLinePrimitive'
import { ChannelPrimitive } from './primitives/ChannelPrimitive'
import { RectanglePrimitive } from './primitives/RectanglePrimitive'
import { TextLabelPrimitive } from './primitives/TextLabelPrimitive'
import { FibRetracementPrimitive } from './primitives/FibRetracementPrimitive'
import { FibExtensionPrimitive } from './primitives/FibExtensionPrimitive'
import { FibFanPrimitive } from './primitives/FibFanPrimitive'
import { FibTimeZonesPrimitive } from './primitives/FibTimeZonesPrimitive'
import { PitchforkPrimitive } from './primitives/PitchforkPrimitive'
import { ElliottWavePrimitive } from './primitives/ElliottWavePrimitive'
import { ArrowUpPrimitive, ArrowDownPrimitive } from './primitives/ArrowPrimitive'
import { MeasureLinePrimitive } from './primitives/MeasureLinePrimitive'

function createPrimitive(drawing: Drawing): BasePrimitive {
  switch (drawing.tool) {
    case 'hline': return new HLinePrimitive(drawing)
    case 'vline': return new VLinePrimitive(drawing)
    case 'ray': return new RayPrimitive(drawing)
    case 'extended_line': return new ExtendedLinePrimitive(drawing)
    case 'trendline': return new TrendLinePrimitive(drawing)
    case 'channel': return new ChannelPrimitive(drawing)
    case 'rect': return new RectanglePrimitive(drawing)
    case 'textlabel': return new TextLabelPrimitive(drawing)
    case 'arrow_up': return new ArrowUpPrimitive(drawing)
    case 'arrow_down': return new ArrowDownPrimitive(drawing)
    case 'fib_ret': return new FibRetracementPrimitive(drawing)
    case 'fib_ext': return new FibExtensionPrimitive(drawing)
    case 'fib_fan': return new FibFanPrimitive(drawing)
    case 'fib_timezones': return new FibTimeZonesPrimitive(drawing)
    case 'pitchfork': return new PitchforkPrimitive(drawing)
    case 'elliott': return new ElliottWavePrimitive(drawing)
    case 'measure': return new MeasureLinePrimitive(drawing)
  }
}

export class DrawingManager {
  private _series: ISeriesApi<'Candlestick'>
  private _chart: IChartApi
  private _primitives = new Map<string, BasePrimitive>()
  private _drawings = new Map<string, Drawing>()

  constructor(series: ISeriesApi<'Candlestick'>, chart: IChartApi) {
    this._series = series
    this._chart = chart
  }

  add(drawing: Drawing): void {
    if (this._primitives.has(drawing.id)) {
      this.update(drawing.id, drawing)
      return
    }
    const primitive = createPrimitive(drawing)
    this._primitives.set(drawing.id, primitive)
    this._drawings.set(drawing.id, drawing)
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    ;(this._series as any).attachPrimitive(primitive)
    // Request chart redraw
    this._chart.applyOptions({})
  }

  remove(id: string): void {
    const primitive = this._primitives.get(id)
    if (!primitive) return
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    ;(this._series as any).detachPrimitive(primitive)
    this._primitives.delete(id)
    this._drawings.delete(id)
    this._chart.applyOptions({})
  }

  update(id: string, patch: Partial<Drawing>): void {
    const existing = this._drawings.get(id)
    if (!existing) return
    const updated = { ...existing, ...patch }
    this._drawings.set(id, updated)
    this._primitives.get(id)?.updateData(updated)
    this._chart.applyOptions({})
  }

  getAll(): Drawing[] {
    return [...this._drawings.values()]
  }

  clear(): void {
    for (const [id] of this._primitives) {
      this.remove(id)
    }
  }
}
