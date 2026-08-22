/**
 * Shared chart-building helpers for rendering an order's trade on a candle chart —
 * used by Orderbook's own chart today and by ChartAnalysis's order-focus mode.
 * Extracted from Orderbook.tsx so both views build price lines/markers the same way
 * instead of duplicating this logic.
 */
import type { AnalysisRecord, CandleBar, OrderbookEntryDetail, OrderbookEntrySummary } from '@/api/client'
import type { ForexChartMarker, ForexChartPriceLine } from '@/components/charts/ForexChart'

export function getTradeStartAt(
  entry: Pick<OrderbookEntrySummary, 'requested_at' | 'opened_at'> | null | undefined,
): string | null {
  return entry?.opened_at ?? entry?.requested_at ?? null
}

export function getTradeEndAt(entry: Pick<OrderbookEntrySummary, 'closed_at'> | null | undefined): string | null {
  return entry?.closed_at ?? null
}

export function findMarkerTimestamp(
  candles: CandleBar[],
  targetTimestamp: string | null,
  targetPrice?: number | null,
): string | null {
  if (!targetTimestamp || candles.length === 0) return null
  const targetMs = new Date(targetTimestamp).getTime()
  if (!Number.isFinite(targetMs)) return null

  const times = candles.map(c => new Date(c.timestamp).getTime()).filter(Number.isFinite)
  if (times.length === 0) return null
  const minMs = Math.min(...times)
  const maxMs = Math.max(...times)
  const sortedTimes = [...times].sort((a, b) => a - b)
  const interval = sortedTimes.length > 1 ? sortedTimes[1] - sortedTimes[0] : 0
  const tolerance = interval / 2
  // Target falls outside the loaded candle range (even accounting for half a bar of
  // slack) — there is no candle data to anchor this marker to, so don't show it
  // rather than snapping it onto whichever edge candle happens to be closest.
  if (targetMs < minMs - tolerance || targetMs > maxMs + tolerance) return null

  const byTime = [...candles].sort(
    (left, right) =>
      Math.abs(new Date(left.timestamp).getTime() - targetMs) -
      Math.abs(new Date(right.timestamp).getTime() - targetMs),
  )
  const nearby = byTime.slice(0, Math.min(8, byTime.length))

  if (typeof targetPrice === 'number' && Number.isFinite(targetPrice)) {
    const containing = nearby.find(candle => candle.low <= targetPrice && candle.high >= targetPrice)
    if (containing) return containing.timestamp
  }

  return byTime[0]?.timestamp ?? null
}

export function buildOrderPriceLines(entry: OrderbookEntryDetail | null): ForexChartPriceLine[] {
  if (!entry) return []
  const overlays = entry.analysis_overlays?.levels ?? {}
  const lines: ForexChartPriceLine[] = []
  if (typeof entry.fill_price === 'number') {
    lines.push({ price: entry.fill_price, title: 'Entry', color: '#38bdf8' })
  } else {
    lines.push({ price: entry.requested_price, title: 'Requested', color: '#38bdf8' })
  }
  if (typeof entry.close_price === 'number') {
    lines.push({ price: entry.close_price, title: 'Exit', color: '#f59e0b' })
  }
  if (typeof entry.stop_loss === 'number') {
    lines.push({ price: entry.stop_loss, title: 'SL', color: '#ef4444' })
  }
  if (typeof entry.take_profit === 'number') {
    lines.push({ price: entry.take_profit, title: 'TP', color: '#22c55e' })
  }
  for (const value of overlays.support ?? []) {
    lines.push({ price: value, title: 'Support', color: '#14b8a6' })
  }
  for (const value of overlays.resistance ?? []) {
    lines.push({ price: value, title: 'Resistance', color: '#a855f7' })
  }
  return lines
}

export function buildOrderMarkers(entry: OrderbookEntryDetail | null, candles: CandleBar[]): ForexChartMarker[] {
  if (!entry || candles.length === 0) return []
  const entryPrice = entry.fill_price ?? entry.requested_price
  const requestedTime = findMarkerTimestamp(candles, getTradeStartAt(entry), entryPrice)
  const closedTime = findMarkerTimestamp(candles, getTradeEndAt(entry), entry.close_price)
  const markers: ForexChartMarker[] = []
  if (requestedTime) {
    markers.push({
      timestamp: requestedTime,
      position: entry.direction === 'BUY' ? 'belowBar' : 'aboveBar',
      shape: entry.direction === 'BUY' ? 'arrowUp' : 'arrowDown',
      color: '#38bdf8',
      text: 'Start',
      emphasis: true,
    })
  }
  if (closedTime) {
    markers.push({
      timestamp: closedTime,
      position: entry.direction === 'BUY' ? 'aboveBar' : 'belowBar',
      shape: 'circle',
      color: '#f59e0b',
      text: 'End',
      emphasis: true,
    })
  }
  return markers
}

export function buildOrderAnalysisMarkers(records: AnalysisRecord[], candles: CandleBar[]): ForexChartMarker[] {
  const markers: Array<ForexChartMarker | null> = records
    .map(record => {
      const timestamp = findMarkerTimestamp(candles, record.decided_at, null)
      if (!timestamp) return null
      const biasMatch = /"primary_bias"\s*:\s*"(BIAS_LONG|BIAS_SHORT|BIAS_NEUTRAL|BIAS_REVERSAL_LONG|BIAS_REVERSAL_SHORT)"/i.exec(
        record.analysis_text ?? JSON.stringify(record.output ?? {}),
      )
      const bias = biasMatch?.[1]?.toUpperCase() ?? ''
      const label = bias.includes('LONG') ? 'U' : bias.includes('SHORT') ? 'D' : 'N'
      const conf = record.confidence != null ? Math.round(record.confidence * 100) + '%' : null
      const text = conf != null ? label + '\n' + conf : label
      return {
        timestamp,
        position: 'belowBar',
        shape: 'square',
        color: '#fb923c',
        text,
        payload: record,
      } satisfies ForexChartMarker
    })
  return markers.filter((marker): marker is ForexChartMarker => marker !== null)
}
