import type { CandleBar, IndicatorValue } from '@/api/client'

export const TF_MINUTES: Record<string, number> = {
  M5: 5, M15: 15, M30: 30, H1: 60, H4: 240, D1: 1440,
}

function asSorted(candles: CandleBar[]): CandleBar[] {
  return [...candles].sort((a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime())
}

/** Aggregate finer candles into coarser TF buckets (UTC-aligned). No-op if toTf is finer or equal. */
export function resampleCandles(candles: CandleBar[], toTf: string): CandleBar[] {
  const toSec = (TF_MINUTES[toTf] ?? 0) * 60
  if (!toSec) return candles
  const sorted = asSorted(candles)
  const groups = new Map<number, CandleBar[]>()
  for (const c of sorted) {
    const ts = Math.floor(new Date(c.timestamp).getTime() / 1000)
    const bucket = Math.floor(ts / toSec) * toSec
    if (!groups.has(bucket)) groups.set(bucket, [])
    groups.get(bucket)!.push(c)
  }
  return Array.from(groups.entries())
    .sort(([a], [b]) => a - b)
    .map(([bucket, bars]) => ({
      timestamp: new Date(bucket * 1000).toISOString(),
      open: bars[0].open,
      high: Math.max(...bars.map(b => b.high)),
      low: Math.min(...bars.map(b => b.low)),
      close: bars[bars.length - 1].close,
      tick_volume: bars.reduce((s, b) => s + b.tick_volume, 0),
      spread: bars[bars.length - 1].spread,
    }))
}

/** How many chart-TF candles are needed to warm up an indicator of given period on indicatorTf. */
export function warmupCount(period: number, indicatorTf: string, chartTf: string): number {
  const indMin = TF_MINUTES[indicatorTf] ?? TF_MINUTES[chartTf] ?? 5
  const chartMin = TF_MINUTES[chartTf] ?? 5
  if (indMin <= chartMin) return period
  return Math.ceil(period * indMin / chartMin)
}

export function calcSma(candles: CandleBar[], period: number): IndicatorValue[] {
  if (period < 1) return []
  const data = asSorted(candles)
  const out: IndicatorValue[] = []
  for (let i = period - 1; i < data.length; i++) {
    const avg = data.slice(i - period + 1, i + 1).reduce((s, c) => s + c.close, 0) / period
    out.push({ timestamp: data[i].timestamp, value: avg })
  }
  return out
}

export function calcEma(candles: CandleBar[], period: number): IndicatorValue[] {
  if (period < 1) return []
  const data = asSorted(candles)
  if (data.length === 0) return []
  const k = 2 / (period + 1)
  let ema = data[0].close
  const out: IndicatorValue[] = [{ timestamp: data[0].timestamp, value: ema }]
  for (let i = 1; i < data.length; i++) {
    ema = data[i].close * k + ema * (1 - k)
    out.push({ timestamp: data[i].timestamp, value: ema })
  }
  return out
}

export function calcRsi(candles: CandleBar[], period: number): IndicatorValue[] {
  if (period < 1) return []
  const data = asSorted(candles)
  if (data.length < period + 1) return []
  let avgGain = 0
  let avgLoss = 0
  for (let i = 1; i <= period; i++) {
    const d = data[i].close - data[i - 1].close
    if (d > 0) avgGain += d; else avgLoss -= d
  }
  avgGain /= period
  avgLoss /= period
  const toRsi = (g: number, l: number) => l === 0 ? 100 : 100 - 100 / (1 + g / l)
  const out: IndicatorValue[] = [{ timestamp: data[period].timestamp, value: toRsi(avgGain, avgLoss) }]
  for (let i = period + 1; i < data.length; i++) {
    const d = data[i].close - data[i - 1].close
    avgGain = (avgGain * (period - 1) + (d > 0 ? d : 0)) / period
    avgLoss = (avgLoss * (period - 1) + (d < 0 ? -d : 0)) / period
    out.push({ timestamp: data[i].timestamp, value: toRsi(avgGain, avgLoss) })
  }
  return out
}

export function calcAtr(candles: CandleBar[], period: number): IndicatorValue[] {
  if (period < 1) return []
  const data = asSorted(candles)
  if (data.length < period) return []
  const tr = (i: number) =>
    i === 0
      ? data[0].high - data[0].low
      : Math.max(
          data[i].high - data[i].low,
          Math.abs(data[i].high - data[i - 1].close),
          Math.abs(data[i].low - data[i - 1].close),
        )
  let atr = Array.from({ length: period }, (_, i) => tr(i)).reduce((s, v) => s + v, 0) / period
  const out: IndicatorValue[] = [{ timestamp: data[period - 1].timestamp, value: atr }]
  for (let i = period; i < data.length; i++) {
    atr = (atr * (period - 1) + tr(i)) / period
    out.push({ timestamp: data[i].timestamp, value: atr })
  }
  return out
}
