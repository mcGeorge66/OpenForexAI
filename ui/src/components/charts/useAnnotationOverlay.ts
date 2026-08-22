/**
 * Renders LLM-drawn chart annotations (zone_marker/trade_marker/candle_marker tool
 * calls, returned by POST /prompt-workbench/chat as `annotations`/`removed_annotation_ids`)
 * onto a ForexChart. Extracted from PromptWorkbench.tsx so other callers (e.g. the
 * Chart Analysis assistant) render the exact same annotations the Simulation tab
 * already does, instead of a second implementation. Zones and closed-trade lines are
 * drawn via the existing rect/trendline DrawingManager primitives (imperative
 * chartRef.add/removeDrawing); open trade legs and single-candle markers are surfaced
 * as ForexChartMarker[] for the caller to merge into <ForexChart markers={...}>.
 */
import { useCallback, useEffect, useMemo, useRef, useState, type RefObject } from 'react'
import { LineStyle, type UTCTimestamp } from 'lightweight-charts'
import type {
  CandleBar,
  PromptWorkbenchAnnotation,
  PromptWorkbenchAnnotationRemoval,
  PromptWorkbenchChatResponse,
} from '@/api/client'
import type { ForexChartHandle, ForexChartMarker } from '@/components/charts/ForexChart'
import type { Drawing } from '@/components/charts/drawing/types'

export function toUnixTime(iso: string): UTCTimestamp {
  return Math.floor(new Date(iso).getTime() / 1000) as UTCTimestamp
}

export function pipSize(price: number): number {
  return price > 20 ? 0.01 : 0.0001
}

export const DEFAULT_ANNOTATION_COLOR = '#f59e0b'

// Tagged with the color selected at send time, so overlapping results from
// different questions/runs stay visually distinguishable on the chart.
export type TaggedAnnotation = PromptWorkbenchAnnotation & { _color: string }

// Identifies an annotation for upsert-by-id merging: a `change`/`new` call with
// the same key replaces the previous entry instead of piling up next to it. A
// trade's open and close legs share a trade_id but are corrected independently,
// hence the `action` suffix — everything else has exactly one record per id.
function annotationKey(a: { kind: string }): string {
  if (a.kind === 'zone') return `zone:${(a as Extract<PromptWorkbenchAnnotation, { kind: 'zone' }>).zone_id}`
  if (a.kind === 'candle_marker') return `candle_marker:${(a as Extract<PromptWorkbenchAnnotation, { kind: 'candle_marker' }>).marker_id}`
  const trade = a as Extract<PromptWorkbenchAnnotation, { kind: 'trade' }>
  return `trade:${trade.trade_id}:${trade.action}`
}

function removalKey(r: PromptWorkbenchAnnotationRemoval): string {
  if (r.kind === 'zone') return `zone:${r.zone_id}`
  if (r.kind === 'candle_marker') return `candle_marker:${r.marker_id}`
  return `trade:${r.trade_id}:${r.action}`
}

export interface AnnotationOverlay {
  annotations: TaggedAnnotation[]
  /** Always mirrors `annotations` — for callers that need the latest value inside a
   * closure captured before a state update would normally re-render (e.g. a tight
   * step loop), without re-subscribing to the array on every change. */
  annotationsRef: RefObject<TaggedAnnotation[]>
  annotationColor: string
  setAnnotationColor: (color: string) => void
  clearAnnotations: () => void
  tagAnnotations: (list: PromptWorkbenchAnnotation[]) => TaggedAnnotation[]
  /** Applies one turn's worth of annotation changes from a /prompt-workbench/chat
   * response: op='new'/'change' upserts by id, op='delete' drops it. */
  applyAnnotationUpdates: (resp: Pick<PromptWorkbenchChatResponse, 'annotations' | 'removed_annotation_ids'>) => void
  /** Open trade legs + single-candle markers, ready to merge into <ForexChart markers>.
   * Zones and closed-trade lines are drawn directly onto `chartRef` instead (imperative
   * DrawingManager primitives), so they are not part of this array. */
  markers: ForexChartMarker[]
}

export function useAnnotationOverlay(
  chartRef: RefObject<ForexChartHandle | null>,
  candles: CandleBar[],
): AnnotationOverlay {
  const [annotations, setAnnotations] = useState<TaggedAnnotation[]>([])
  const annotationsRef = useRef<TaggedAnnotation[]>(annotations)
  useEffect(() => { annotationsRef.current = annotations }, [annotations])
  const renderedDrawingIdsRef = useRef<Set<string>>(new Set())
  const renderedDrawingContentRef = useRef<Map<string, string>>(new Map())
  const [annotationColor, setAnnotationColor] = useState(DEFAULT_ANNOTATION_COLOR)

  const clearAnnotations = useCallback(() => {
    for (const drawing of chartRef.current?.getDrawings() ?? []) {
      chartRef.current?.removeDrawing(drawing.id)
    }
    renderedDrawingIdsRef.current.clear()
    renderedDrawingContentRef.current.clear()
    setAnnotations([])
  }, [chartRef])

  const tagAnnotations = useCallback(
    (list: PromptWorkbenchAnnotation[]): TaggedAnnotation[] => list.map(a => ({ ...a, _color: annotationColor })),
    [annotationColor],
  )

  const applyAnnotationUpdates = useCallback((resp: Pick<PromptWorkbenchChatResponse, 'annotations' | 'removed_annotation_ids'>) => {
    if (!resp.annotations?.length && !resp.removed_annotation_ids?.length) return
    const removedKeys = new Set((resp.removed_annotation_ids ?? []).map(removalKey))
    const incoming = tagAnnotations(resp.annotations ?? [])
    const incomingKeys = new Set(incoming.map(annotationKey))
    setAnnotations(prev => [
      ...prev.filter(a => !removedKeys.has(annotationKey(a)) && !incomingKeys.has(annotationKey(a))),
      ...incoming,
    ])
  }, [tagAnnotations])

  const tradeMarkers: ForexChartMarker[] = useMemo(() => annotations
    .filter((a): a is Extract<TaggedAnnotation, { kind: 'trade' }> => a.kind === 'trade')
    .map(a => ({
      timestamp: a.timestamp,
      position: a.action === 'open' ? 'belowBar' : 'aboveBar',
      shape: a.action === 'open' ? (a.direction === 'short' ? 'arrowDown' : 'arrowUp') : 'circle',
      color: a._color,
      // Line 1: ID + direction/action as single letters (S/L, O/C) + candle number.
      // Line 2 (if present): the free-text note — its own line via CustomSeriesMarkers.
      text: (() => {
        const dirLetter = a.direction === 'short' ? 'S' : a.direction === 'long' ? 'L' : ''
        const actionLetter = a.action === 'open' ? 'O' : 'C'
        const line1 = `[${a.trade_id}] ${dirLetter}${actionLetter} #${a.candle_number}`
        return a.note ? `${line1}\n${a.note}` : line1
      })(),
    })), [annotations])

  const candleMarkers: ForexChartMarker[] = useMemo(() => annotations
    .filter((a): a is Extract<TaggedAnnotation, { kind: 'candle_marker' }> => a.kind === 'candle_marker')
    .map(a => ({
      timestamp: a.timestamp,
      position: a.position === 'above' ? 'aboveBar' : 'belowBar',
      shape: a.position === 'above' ? 'arrowDown' : 'arrowUp',
      color: a._color,
      text: `[${a.marker_id}] #${a.candle_number} ${a.text}`,
    })), [annotations])

  // Draw/update/remove zones and closed-trade lines as annotations change —
  // DrawingManager is imperative (chartRef.add/removeDrawing), so this diffs
  // against what's already on the chart: unchanged content is left alone, a
  // corrected (op='change') zone/trade is removed and redrawn, and one that
  // dropped out of `annotations` (op='delete') is removed outright.
  useEffect(() => {
    const zonesById = new Map<string, Extract<TaggedAnnotation, { kind: 'zone' }>>()
    const opensByTradeId = new Map<string, Extract<TaggedAnnotation, { kind: 'trade' }>>()
    const closedTradeIds = new Set<string>()
    for (const a of annotations) {
      if (a.kind === 'zone') zonesById.set(a.zone_id, a)
      else if (a.kind === 'trade' && a.action === 'open') opensByTradeId.set(a.trade_id, a)
      else if (a.kind === 'trade' && a.action === 'close') closedTradeIds.add(a.trade_id)
    }

    // Drop drawings whose annotation no longer exists (deleted) or whose
    // matching leg disappeared (a closed trade's line needs both legs present).
    for (const drawingId of [...renderedDrawingIdsRef.current]) {
      const stillWanted = drawingId.startsWith('zone_')
        ? zonesById.has(drawingId.slice(5))
        : drawingId.startsWith('trade_')
          ? opensByTradeId.has(drawingId.slice(6)) && closedTradeIds.has(drawingId.slice(6))
          : true
      if (!stillWanted) {
        chartRef.current?.removeDrawing(drawingId)
        renderedDrawingIdsRef.current.delete(drawingId)
        renderedDrawingContentRef.current.delete(drawingId)
      }
    }

    for (const zone of zonesById.values()) {
      const drawingId = `zone_${zone.zone_id}`
      const startMs = new Date(zone.start_timestamp).getTime()
      const endMs = new Date(zone.end_timestamp).getTime()
      const inRange = candles.filter(c => {
        const t = new Date(c.timestamp).getTime()
        return t >= Math.min(startMs, endMs) && t <= Math.max(startMs, endMs)
      })
      if (inRange.length === 0) continue
      const contentKey = `${zone.start_timestamp}|${zone.end_timestamp}|${zone.heading}|${zone._color}`
      if (renderedDrawingContentRef.current.get(drawingId) === contentKey) continue
      if (renderedDrawingIdsRef.current.has(drawingId)) chartRef.current?.removeDrawing(drawingId)
      const high = Math.max(...inRange.map(c => c.high))
      const low = Math.min(...inRange.map(c => c.low))
      const heightPips = (high - low) / pipSize(high)
      const drawing: Drawing = {
        id: drawingId,
        tool: 'rect',
        points: [
          { time: toUnixTime(zone.start_timestamp), price: high },
          { time: toUnixTime(zone.end_timestamp), price: low },
        ],
        style: { color: zone._color, lineStyle: LineStyle.Solid, lineWidth: 1, fillColor: zone._color, fillOpacity: 0.12 },
        label: `[${zone.zone_id}] ${zone.heading}`,
        sublabel: `#${zone.start_candle_number}–#${zone.end_candle_number} · ${inRange.length} candles, ${heightPips.toFixed(1)} pips`,
        visible: true,
        selected: false,
      }
      chartRef.current?.addDrawing(drawing)
      renderedDrawingIdsRef.current.add(drawingId)
      renderedDrawingContentRef.current.set(drawingId, contentKey)
    }

    for (const a of annotations) {
      if (a.kind !== 'trade' || a.action !== 'close') continue
      const openAnn = opensByTradeId.get(a.trade_id)
      if (!openAnn) continue
      const drawingId = `trade_${a.trade_id}`
      const contentKey = `${openAnn.timestamp}|${openAnn.price}|${openAnn.direction}|${a.timestamp}|${a.price}|${openAnn._color}`
      if (renderedDrawingContentRef.current.get(drawingId) === contentKey) continue
      if (renderedDrawingIdsRef.current.has(drawingId)) chartRef.current?.removeDrawing(drawingId)
      const candleCountSpan = Math.abs(openAnn.candle_number - a.candle_number)
      const priceDiff = openAnn.direction === 'short' ? openAnn.price - a.price : a.price - openAnn.price
      const pips = priceDiff / pipSize(a.price)
      const drawing: Drawing = {
        id: drawingId,
        tool: 'trendline',
        points: [
          { time: toUnixTime(openAnn.timestamp), price: openAnn.price },
          { time: toUnixTime(a.timestamp), price: a.price },
        ],
        style: { color: openAnn._color, lineStyle: LineStyle.Solid, lineWidth: 2 },
        label: `${candleCountSpan} candles, ${pips >= 0 ? '+' : ''}${pips.toFixed(1)} pips`,
        visible: true,
        selected: false,
      }
      chartRef.current?.addDrawing(drawing)
      renderedDrawingIdsRef.current.add(drawingId)
      renderedDrawingContentRef.current.set(drawingId, contentKey)
    }
  }, [annotations, candles, chartRef])

  const markers = useMemo(() => [...tradeMarkers, ...candleMarkers], [tradeMarkers, candleMarkers])

  return {
    annotations, annotationsRef, annotationColor, setAnnotationColor,
    clearAnnotations, tagAnnotations, applyAnnotationUpdates, markers,
  }
}
