/**
 * Orderbook → Performance tab.
 *
 * One cumulative-P&L curve per currency pair: every realised trade of the
 * chosen period added up in the order it was closed. The question "is there
 * more or less left at the end" is then answered by where the line ends, not
 * by reading every single win and loss out of the table.
 *
 * The pairs are deliberately kept apart — no combined curve. A sum over pairs
 * hides which of them actually carries the result.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { AlertTriangle, RefreshCcw } from 'lucide-react'
import {
  CrosshairMode,
  LineSeries,
  LineStyle,
  createChart,
  type IChartApi,
  type ISeriesApi,
  type UTCTimestamp,
} from 'lightweight-charts'

import { api, type OrderbookEntrySummary } from '@/api/client'
import { getUiUtcOffset } from '@/utils/time'

/** GET /orderbook clamps `limit` to 1000 rows per broker — see
 *  `_serialize_order_book_entry`'s caller in `management/api.py`. Anything
 *  older than the 1000th newest order cannot be fetched through this route, so
 *  the header says so out loud when the limit was actually reached. */
const FETCH_LIMIT = 1000

type PeriodKey = '7d' | '30d' | '90d' | 'all'

const PERIODS: { key: PeriodKey; label: string; days: number | null }[] = [
  { key: '7d', label: '7 days', days: 7 },
  { key: '30d', label: '30 days', days: 30 },
  { key: '90d', label: '90 days', days: 90 },
  { key: 'all', label: 'all', days: null },
]

interface CurvePoint {
  time: UTCTimestamp
  value: number
}

/** What the cursor is standing on: not just the height of the curve, but the
 *  trade that moved it to there. Kept beside the curve rather than inside the
 *  chart data, because lightweight-charts only ever reads time and value. */
interface PointMeta {
  pnl: number
  pips: number | null
  cumulative: number
  merged: number
  direction: string | null
  orderId: string | null
}

interface PairCurve {
  pair: string
  points: CurvePoint[]
  meta: Map<number, PointMeta>
  trades: number
  withoutResult: number
  total: number
  wins: number
  losses: number
  best: number
  worst: number
  maxDrawdown: number
  firstAt: number
  lastAt: number
}

function money(value: number): string {
  return `${value >= 0 ? '+' : ''}${value.toFixed(2)} $`
}

function uiClock(unixSeconds: number): Date {
  return new Date(unixSeconds * 1000 + getUiUtcOffset() * 3_600_000)
}

function pad2(n: number): string {
  return n < 10 ? `0${n}` : String(n)
}

/** "09-16" — axis ticks over days, so the date matters, not the minute. */
function chartDate(unixSeconds: number): string {
  const ui = uiClock(unixSeconds)
  return `${pad2(ui.getUTCMonth() + 1)}-${pad2(ui.getUTCDate())}`
}

/** "09-16 14:35" — crosshair readout, where the minute does matter. */
function chartDateTime(unixSeconds: number): string {
  const ui = uiClock(unixSeconds)
  return `${pad2(ui.getUTCMonth() + 1)}-${pad2(ui.getUTCDate())} ${pad2(ui.getUTCHours())}:${pad2(ui.getUTCMinutes())}`
}

/** The moment the result became real. Every row carrying a P&L has one of
 *  these two timestamps — checked against the live table, 1021 of 1021. */
function realisedAt(entry: OrderbookEntrySummary): string | null {
  return entry.closed_at ?? entry.close_requested_at ?? null
}

function buildCurves(entries: OrderbookEntrySummary[], days: number | null): PairCurve[] {
  const cutoff = days === null ? null : Date.now() - days * 86_400_000

  const byPair = new Map<string, OrderbookEntrySummary[]>()
  const withoutResult = new Map<string, number>()
  for (const entry of entries) {
    const pair = entry.pair || '?'
    const stamp = realisedAt(entry)
    const reference = stamp ?? entry.requested_at
    if (cutoff !== null && reference && new Date(reference).getTime() < cutoff) continue
    if (typeof entry.pnl_account_currency !== 'number' || !stamp) {
      withoutResult.set(pair, (withoutResult.get(pair) ?? 0) + 1)
      continue
    }
    const list = byPair.get(pair)
    if (list) list.push(entry)
    else byPair.set(pair, [entry])
  }

  const curves: PairCurve[] = []
  for (const [pair, list] of byPair) {
    const sorted = [...list].sort(
      (a, b) => new Date(realisedAt(a)!).getTime() - new Date(realisedAt(b)!).getTime(),
    )
    const points: CurvePoint[] = []
    const meta = new Map<number, PointMeta>()
    let running = 0
    let peak = 0
    let maxDrawdown = 0
    let wins = 0
    let losses = 0
    let best = Number.NEGATIVE_INFINITY
    let worst = Number.POSITIVE_INFINITY

    for (const entry of sorted) {
      const pnl = entry.pnl_account_currency as number
      running += pnl
      if (pnl > 0) wins += 1
      else if (pnl < 0) losses += 1
      if (pnl > best) best = pnl
      if (pnl < worst) worst = pnl
      if (running > peak) peak = running
      if (peak - running > maxDrawdown) maxDrawdown = peak - running

      const time = Math.floor(new Date(realisedAt(entry)!).getTime() / 1000) as UTCTimestamp
      const last = points[points.length - 1]
      const previous = meta.get(time)
      // Two trades closed in the same second would be a duplicate time, which
      // lightweight-charts rejects. Both belong in the sum, so the second one
      // joins the point instead of adding one — and the readout then says so
      // instead of naming one of the two trades as if it were alone.
      if (last && last.time === time && previous) {
        last.value = running
        meta.set(time, {
          pnl: previous.pnl + pnl,
          pips: null,
          cumulative: running,
          merged: previous.merged + 1,
          direction: null,
          orderId: null,
        })
      } else {
        points.push({ time, value: running })
        meta.set(time, {
          pnl,
          pips: typeof entry.pnl_pips === 'number' ? entry.pnl_pips : null,
          cumulative: running,
          merged: 1,
          direction: entry.direction || null,
          orderId: entry.broker_order_id ?? null,
        })
      }
    }

    curves.push({
      pair,
      points,
      meta,
      trades: sorted.length,
      withoutResult: withoutResult.get(pair) ?? 0,
      total: running,
      wins,
      losses,
      best: best === Number.NEGATIVE_INFINITY ? 0 : best,
      worst: worst === Number.POSITIVE_INFINITY ? 0 : worst,
      maxDrawdown,
      firstAt: points[0]?.time ?? 0,
      lastAt: points[points.length - 1]?.time ?? 0,
    })
  }

  curves.sort((a, b) => a.pair.localeCompare(b.pair))
  return curves
}

interface HoverState {
  x: number
  y: number
  meta: PointMeta
  time: number
}

function EquityChart({
  points,
  meta,
  positive,
  pair,
}: {
  points: CurvePoint[]
  meta: Map<number, PointMeta>
  positive: boolean
  pair: string
}) {
  const hostRef = useRef<HTMLDivElement | null>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const seriesRef = useRef<ISeriesApi<'Line'> | null>(null)
  // The crosshair subscription is set up once, but it has to read the current
  // period's trades — hence a ref, not the captured prop.
  const metaRef = useRef(meta)
  metaRef.current = meta
  const [hover, setHover] = useState<HoverState | null>(null)

  useEffect(() => {
    const el = hostRef.current
    if (!el) return
    const chart = createChart(el, {
      width: el.clientWidth,
      height: el.clientHeight || 220,
      layout: {
        background: { color: '#ffffff' },
        textColor: '#111827',
        attributionLogo: false,
      },
      localization: {
        timeFormatter: (time: unknown) => chartDateTime(Number(time)),
        priceFormatter: (price: number) => price.toFixed(2),
      },
      grid: {
        vertLines: { color: '#f3f4f6' },
        horzLines: { color: '#e5e7eb' },
      },
      timeScale: {
        borderColor: '#9ca3af',
        timeVisible: false,
        secondsVisible: false,
        tickMarkFormatter: (time: unknown) => chartDate(Number(time)),
      },
      rightPriceScale: { borderColor: '#9ca3af' },
      handleScroll: { mouseWheel: false, pressedMouseMove: true },
      handleScale: { mouseWheel: true, pinch: true, axisDoubleClickReset: true },
      // Magnet: the crosshair sits on the trade nearest to the pointer, so the
      // readout below always belongs to a real trade and not to empty space.
      crosshair: {
        mode: CrosshairMode.Magnet,
        vertLine: { color: '#6b7280', labelBackgroundColor: '#111827' },
        horzLine: { color: '#6b7280', labelBackgroundColor: '#111827' },
      },
    })
    const series = chart.addSeries(LineSeries, {
      color: '#059669',
      lineWidth: 2,
      priceLineVisible: false,
      // The end value is already in the card header, in bigger type. On the
      // axis it only covers up a scale label.
      lastValueVisible: false,
    })
    // The break-even line: above it the period is in profit, below it is not.
    series.createPriceLine({
      price: 0,
      color: '#6b7280',
      lineWidth: 1,
      lineStyle: LineStyle.Dashed,
      axisLabelVisible: true,
      title: '0',
    })
    chartRef.current = chart
    seriesRef.current = series

    chart.subscribeCrosshairMove(param => {
      const point = param.point
      if (!point || param.time === undefined || point.x < 0 || point.y < 0) {
        setHover(null)
        return
      }
      const time = Number(param.time)
      const found = metaRef.current.get(time)
      if (!found) {
        setHover(null)
        return
      }
      setHover({ x: point.x, y: point.y, meta: found, time })
    })

    const observer = new ResizeObserver(() => {
      if (!hostRef.current) return
      chart.applyOptions({
        width: hostRef.current.clientWidth,
        height: hostRef.current.clientHeight || 220,
      })
    })
    observer.observe(el)

    return () => {
      observer.disconnect()
      chart.remove()
      chartRef.current = null
      seriesRef.current = null
    }
  }, [])

  useEffect(() => {
    const series = seriesRef.current
    if (!series) return
    series.applyOptions({ color: positive ? '#059669' : '#dc2626' })
    series.setData(points)
    chartRef.current?.timeScale().fitContent()
    setHover(null)
  }, [points, positive])

  // Flipped to the left of the pointer near the right edge, and pushed down
  // when the curve runs along the top — otherwise the readout would cover the
  // very spot it describes.
  const hostWidth = hostRef.current?.clientWidth ?? 0
  const flipLeft = hover !== null && hostWidth > 0 && hover.x > hostWidth - 190
  const tooltipStyle = hover
    ? {
        left: flipLeft ? undefined : `${hover.x + 14}px`,
        right: flipLeft ? `${Math.max(hostWidth - hover.x + 14, 0)}px` : undefined,
        top: `${Math.min(Math.max(hover.y - 12, 4), 220 - 92)}px`,
      }
    : undefined

  return (
    <div ref={hostRef} className="relative h-[220px] w-full">
      {hover && (
        <div
          className="pointer-events-none absolute z-10 rounded border border-gray-700 bg-gray-950/95 px-2.5 py-1.5 text-xs shadow-lg"
          style={tooltipStyle}
        >
          <div className="text-gray-400 tabular-nums">{chartDateTime(hover.time)}</div>
          <div className="mt-0.5 flex items-baseline gap-2">
            <span className="text-gray-500">
              {hover.meta.merged > 1
                ? `${hover.meta.merged} trades`
                : `${pair} ${hover.meta.direction ?? ''}`.trim()}
            </span>
            <span
              className={[
                'font-semibold tabular-nums',
                hover.meta.pnl >= 0 ? 'text-emerald-400' : 'text-red-400',
              ].join(' ')}
            >
              {money(hover.meta.pnl)}
            </span>
            {hover.meta.pips !== null && (
              <span className="text-gray-500 tabular-nums">
                {hover.meta.pips > 0 ? '+' : ''}{hover.meta.pips.toFixed(1)} Pips
              </span>
            )}
          </div>
          <div className="mt-0.5 text-gray-400 tabular-nums">
            Sum <span className="text-gray-200">{money(hover.meta.cumulative)}</span>
            {hover.meta.orderId && <span className="ml-2 text-gray-600">#{hover.meta.orderId}</span>}
          </div>
        </div>
      )}
    </div>
  )
}

export function OrderbookPerformance() {
  const [entries, setEntries] = useState<OrderbookEntrySummary[]>([])
  const [period, setPeriod] = useState<PeriodKey>('30d')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      // One fetch for the whole history, the period is then cut client-side —
      // switching 7/30/90 days does not hit the backend again.
      const data = await api.getOrderbookEntries({ status_filter: 'all', limit: FETCH_LIMIT })
      setEntries(data)
    } catch (err) {
      setError(String(err))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const days = PERIODS.find(p => p.key === period)?.days ?? null
  const curves = useMemo(() => buildCurves(entries, days), [entries, days])

  const oldestFetched = useMemo(() => {
    let oldest = Number.POSITIVE_INFINITY
    for (const entry of entries) {
      const t = new Date(entry.requested_at).getTime()
      if (Number.isFinite(t) && t < oldest) oldest = t
    }
    return Number.isFinite(oldest) ? oldest : null
  }, [entries])

  const limitReached = entries.length >= FETCH_LIMIT

  return (
    <div className="h-full overflow-auto px-6 py-4">
      <div className="flex items-center justify-between gap-4 mb-3">
        <div className="flex items-center gap-2">
          {PERIODS.map(p => (
            <button
              key={p.key}
              type="button"
              onClick={() => setPeriod(p.key)}
              className={[
                'px-3 py-1 rounded border text-sm whitespace-nowrap',
                period === p.key
                  ? 'border-emerald-500 bg-emerald-900/30 text-emerald-300'
                  : 'border-gray-700 bg-gray-900 text-gray-400 hover:text-gray-200',
              ].join(' ')}
            >
              {p.label}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-3">
          <span className="text-xs text-gray-500 whitespace-nowrap">
            {entries.length} orders loaded
            {oldestFetched !== null && ` · oldest ${chartDate(Math.floor(oldestFetched / 1000))}`}
          </span>
          <button
            type="button"
            onClick={() => void load()}
            className="px-3 py-1 rounded border border-gray-700 bg-gray-900 text-gray-300 hover:text-white flex items-center gap-2 text-sm"
          >
            <RefreshCcw className={loading ? 'w-4 h-4 animate-spin' : 'w-4 h-4'} />
            Refresh
          </button>
        </div>
      </div>

      {error && (
        <div className="mb-3 px-3 py-2 text-sm text-red-400 border border-red-900/40 rounded">{error}</div>
      )}

      {limitReached && (
        <div className="mb-3 px-3 py-2 text-xs text-amber-300 border border-amber-900/40 rounded flex items-start gap-2">
          <AlertTriangle className="w-4 h-4 shrink-0 mt-px" />
          <span>
            The server returns at most {FETCH_LIMIT} orders per request, and that limit was reached.
            Trades older than {oldestFetched !== null ? chartDate(Math.floor(oldestFetched / 1000)) : 'the oldest row shown'} are
            therefore missing from the curves — "all" is not the whole history.
          </span>
        </div>
      )}

      {!loading && curves.length === 0 && (
        <div className="py-12 text-center text-gray-500">No closed trades in this period.</div>
      )}

      <div className="flex flex-col gap-4">
        {curves.map(curve => (
          <section key={curve.pair} className="border border-gray-800 rounded bg-gray-900/40">
            <div className="px-4 py-3 border-b border-gray-800 flex items-baseline justify-between gap-4 flex-wrap">
              <div className="flex items-baseline gap-3">
                <h3 className="text-base font-semibold text-gray-100">{curve.pair}</h3>
                <span
                  className={[
                    'text-lg font-semibold tabular-nums',
                    curve.total >= 0 ? 'text-emerald-400' : 'text-red-400',
                  ].join(' ')}
                  title="Sum of all realised results in this period"
                >
                  {money(curve.total)}
                </span>
              </div>
              <div className="flex items-center gap-4 text-xs text-gray-400 tabular-nums">
                <span title="Trades with a realised result">{curve.trades} trades</span>
                <span title="Winners / losers and the hit rate">
                  {curve.wins} W / {curve.losses} L
                  {curve.trades > 0 && ` · ${Math.round((curve.wins / curve.trades) * 100)}%`}
                </span>
                <span className="text-emerald-500/80" title="Best single trade">{money(curve.best)}</span>
                <span className="text-red-500/80" title="Worst single trade">{money(curve.worst)}</span>
                <span
                  className="text-amber-400/80"
                  title="Largest drop from a high of the curve to the following low"
                >
                  DD {curve.maxDrawdown.toFixed(2)} $
                </span>
              </div>
            </div>
            <div className="px-2 py-2">
              <EquityChart
                points={curve.points}
                meta={curve.meta}
                positive={curve.total >= 0}
                pair={curve.pair}
              />
            </div>
            <div className="px-4 py-2 border-t border-gray-800 text-[11px] text-gray-500">
              {curve.firstAt > 0 && (
                <>
                  {chartDateTime(curve.firstAt)} → {chartDateTime(curve.lastAt)} ·{' '}
                </>
              )}
              added up in closing order
              {curve.withoutResult > 0 && ` · ${curve.withoutResult} orders without a result (rejected or still open) are not in the curve`}
            </div>
          </section>
        ))}
      </div>
    </div>
  )
}
