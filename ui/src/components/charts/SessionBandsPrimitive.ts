import type {
  IChartApi,
  ISeriesPrimitive,
  IPrimitivePaneView,
  IPrimitivePaneRenderer,
  SeriesAttachedParameter,
  UTCTimestamp,
} from 'lightweight-charts'
import { CanvasRenderingTarget2D } from 'fancy-canvas'

export interface SessionBandEntry {
  startTs: number   // unix seconds UTC
  endTs: number     // unix seconds UTC
  color: string     // CSS color (opaque — transparency applied per-row via globalAlpha)
  label: string
  row: number       // 0 = top row (SYD), 1 = TKY, 2 = LON, 3 = NYC
  totalRows: number
}

// Four thin horizontal rows at the TOP of the chart pane — one row per session.
// Every row is independent so overlapping sessions never visually cover each other.
export class SessionBandsPrimitive implements ISeriesPrimitive {
  private _bands: SessionBandEntry[] = []
  private _chart: IChartApi | null = null

  static readonly ROW_HEIGHT_PX = 14  // CSS px per row
  static readonly ALPHA          = 0.55

  updateBands(bands: SessionBandEntry[]): void {
    this._bands = bands
  }

  attached(params: SeriesAttachedParameter): void {
    this._chart = params.chart as unknown as IChartApi
  }

  detached(): void {
    this._chart = null
  }

  paneViews(): readonly IPrimitivePaneView[] {
    const bands     = this._bands
    const chart     = this._chart
    const rowH_px   = SessionBandsPrimitive.ROW_HEIGHT_PX
    const alpha     = SessionBandsPrimitive.ALPHA

    return [{
      renderer(): IPrimitivePaneRenderer {
        return {
          draw(target: CanvasRenderingTarget2D) {
            target.useBitmapCoordinateSpace(scope => {
              if (!chart || bands.length === 0) return
              const { context: ctx, bitmapSize, horizontalPixelRatio, verticalPixelRatio } = scope

              const rowH   = Math.round(rowH_px * verticalPixelRatio)
              const totalRows = bands.length > 0 ? bands[0].totalRows : 1

              const visibleRange = chart.timeScale().getVisibleRange()
              const rangeFrom = visibleRange ? (visibleRange.from as number) : 0
              const rangeTo   = visibleRange ? (visibleRange.to   as number) : Infinity

              ctx.save()
              ctx.globalAlpha = alpha

              for (const band of bands) {
                if (band.endTs <= rangeFrom || band.startTs >= rangeTo) continue

                const coordStart = chart.timeScale().timeToCoordinate(band.startTs as UTCTimestamp)
                const coordEnd   = chart.timeScale().timeToCoordinate(band.endTs   as UTCTimestamp)

                const rawX1 = coordStart !== null
                  ? coordStart * horizontalPixelRatio
                  : band.startTs <= rangeFrom ? -100 : bitmapSize.width + 100

                const rawX2 = coordEnd !== null
                  ? coordEnd * horizontalPixelRatio
                  : band.endTs >= rangeTo ? bitmapSize.width + 100 : -100

                const x1 = Math.max(0, Math.round(rawX1))
                const x2 = Math.min(bitmapSize.width, Math.round(rawX2))
                if (x2 <= x1) continue

                const rowY = band.row * rowH

                ctx.fillStyle = band.color
                ctx.fillRect(x1, rowY, x2 - x1, rowH)
              }

              // Draw 1px separators between rows
              ctx.globalAlpha = 0.3
              ctx.fillStyle = '#000'
              for (let r = 1; r < totalRows; r++) {
                ctx.fillRect(0, r * rowH, bitmapSize.width, 1)
              }

              // Labels at full opacity on top
              ctx.globalAlpha = 1
              const fontSize = Math.round(Math.max(7, rowH * 0.75))
              ctx.font = `bold ${fontSize}px sans-serif`
              ctx.textBaseline = 'middle'
              ctx.textAlign = 'center'

              for (const band of bands) {
                if (band.endTs <= rangeFrom || band.startTs >= rangeTo) continue

                const coordStart = chart.timeScale().timeToCoordinate(band.startTs as UTCTimestamp)
                const coordEnd   = chart.timeScale().timeToCoordinate(band.endTs   as UTCTimestamp)

                const rawX1 = coordStart !== null
                  ? coordStart * horizontalPixelRatio
                  : band.startTs <= rangeFrom ? -100 : bitmapSize.width + 100
                const rawX2 = coordEnd !== null
                  ? coordEnd * horizontalPixelRatio
                  : band.endTs >= rangeTo ? bitmapSize.width + 100 : -100

                const x1 = Math.max(0, Math.round(rawX1))
                const x2 = Math.min(bitmapSize.width, Math.round(rawX2))
                if (x2 <= x1) continue

                const bandWidthCSS = (x2 - x1) / horizontalPixelRatio
                if (bandWidthCSS < 24) continue

                const rowY = band.row * rowH
                ctx.fillStyle = 'rgba(255,255,255,0.9)'
                ctx.fillText(band.label, x1 + (x2 - x1) / 2, rowY + rowH / 2)
              }

              ctx.restore()
            })
          },
        }
      },
    }]
  }
}
