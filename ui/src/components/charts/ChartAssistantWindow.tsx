/**
 * Chart Assistant, as a free-floating window (drag by header, resize from the
 * bottom-right corner) instead of a docked side panel — a docked panel shares
 * width with the chart via flexbox, but the chart's own canvas doesn't reliably
 * shrink to match (lightweight-charts sizes its canvas via ResizeObserver, which
 * can lag or miss a sibling appearing), so the panel could end up visually
 * overlapping the chart's rightmost portion instead of cleanly sharing space.
 * A fixed-position floating window never participates in that layout at all,
 * and lets the user move it out of the way entirely — same proven pattern as
 * OrderInvestigateModal.tsx (Orderbook's "Ask AI" window), duplicated rather
 * than shared since the two have no other logic in common and this keeps each
 * one simple to reason about on its own.
 */
import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { MessageSquare, PictureInPicture2, X } from 'lucide-react'
import type { OrderbookEntryDetail } from '@/api/client'
import type { AnnotationOverlay } from './useAnnotationOverlay'
import { ChartAssistantPanel } from './ChartAssistantPanel'
import type { ChartAssistantContext, ChartAssistantMessage } from './useChartAssistantChat'
import { useDocumentPictureInPicture } from '@/hooks/useDocumentPictureInPicture'

const DEFAULT_WIDTH = 420
const DEFAULT_HEIGHT = 560
const MIN_WIDTH = 320
const MIN_HEIGHT = 280

export interface ChartAssistantWindowProps {
  overlay: AnnotationOverlay
  context: ChartAssistantContext
  focusedOrder: OrderbookEntryDetail | null
  onClose: () => void
  /** Owned by the caller (ChartAnalysis.tsx), not here — that's what makes the chat
   * history survive closing and reopening the whole assistant, not just undock/redock.
   * See useChartAssistantChat.ts's UseChartAssistantChatOptions for the full picture. */
  initialMessages: ChartAssistantMessage[]
  onMessagesChange: (messages: ChartAssistantMessage[]) => void
}

export function ChartAssistantWindow({
  overlay, context, focusedOrder, onClose, initialMessages, onMessagesChange,
}: ChartAssistantWindowProps) {
  const [size, setSize] = useState(() => ({
    width: Math.max(MIN_WIDTH, Math.min(DEFAULT_WIDTH, window.innerWidth - 32)),
    height: Math.max(MIN_HEIGHT, Math.min(DEFAULT_HEIGHT, window.innerHeight - 32)),
  }))
  const [pos, setPos] = useState(() => ({
    x: Math.max(16, window.innerWidth - Math.min(DEFAULT_WIDTH, window.innerWidth - 32) - 24),
    y: 96,
  }))
  const dragState = useRef<{ startX: number; startY: number; origX: number; origY: number } | null>(null)
  const resizeState = useRef<{ startX: number; startY: number; origW: number; origH: number } | null>(null)

  const { pipWindow, open: popOut, close: redock, supported: pipSupported } =
    useDocumentPictureInPicture({ width: size.width, height: size.height })

  // Same global-listener drag/resize pattern as OrderInvestigateModal.
  useEffect(() => {
    const onMouseMove = (e: MouseEvent) => {
      if (dragState.current) {
        const { startX, startY, origX, origY } = dragState.current
        setPos({
          x: Math.min(Math.max(0, origX + (e.clientX - startX)), window.innerWidth - 120),
          y: Math.min(Math.max(0, origY + (e.clientY - startY)), window.innerHeight - 48),
        })
      }
      if (resizeState.current) {
        const { startX, startY, origW, origH } = resizeState.current
        setSize({
          width: Math.max(MIN_WIDTH, origW + (e.clientX - startX)),
          height: Math.max(MIN_HEIGHT, origH + (e.clientY - startY)),
        })
      }
    }
    const onMouseUp = () => { dragState.current = null; resizeState.current = null }
    window.addEventListener('mousemove', onMouseMove)
    window.addEventListener('mouseup', onMouseUp)
    return () => {
      window.removeEventListener('mousemove', onMouseMove)
      window.removeEventListener('mouseup', onMouseUp)
    }
  }, [])

  const startDrag = (e: React.MouseEvent) => {
    dragState.current = { startX: e.clientX, startY: e.clientY, origX: pos.x, origY: pos.y }
  }
  const startResize = (e: React.MouseEvent) => {
    e.stopPropagation()
    resizeState.current = { startX: e.clientX, startY: e.clientY, origW: size.width, origH: size.height }
  }

  const header = (
    <div
      className={`flex items-center justify-between px-3 py-2 bg-gray-900 border-b border-gray-700 flex-shrink-0 select-none ${pipWindow ? '' : 'cursor-move'}`}
      onMouseDown={pipWindow ? undefined : startDrag}
    >
      <div className="flex items-center gap-2 min-w-0">
        <MessageSquare className="w-4 h-4 text-indigo-400 flex-shrink-0" />
        <span className="text-xs font-semibold text-indigo-400 uppercase tracking-wider flex-shrink-0">
          Chart Assistant
        </span>
        {focusedOrder && (
          <span className="text-xs text-gray-400 truncate">
            {focusedOrder.pair} {focusedOrder.direction} · Fill {focusedOrder.fill_price ?? focusedOrder.requested_price} · Close {focusedOrder.close_price ?? '-'}
          </span>
        )}
      </div>
      <div className="flex items-center gap-3 flex-shrink-0">
        {pipWindow ? (
          <button
            onClick={redock}
            onMouseDown={e => e.stopPropagation()}
            title="Zurück ins Browserfenster andocken"
            className="text-gray-500 hover:text-gray-300"
          >
            <PictureInPicture2 className="w-4 h-4" />
          </button>
        ) : (
          <>
            {pipSupported && (
              <button
                onClick={() => void popOut()}
                onMouseDown={e => e.stopPropagation()}
                title="Als eigenes Fenster lösen (aus dem Browser herausziehbar)"
                className="text-gray-500 hover:text-gray-300"
              >
                <PictureInPicture2 className="w-4 h-4" />
              </button>
            )}
            <button
              onClick={onClose}
              onMouseDown={e => e.stopPropagation()}
              className="text-gray-500 hover:text-gray-300"
            >
              <X className="w-4 h-4" />
            </button>
          </>
        )}
      </div>
    </div>
  )

  const body = (
    <div className="flex-1 min-h-0">
      <ChartAssistantPanel
        overlay={overlay}
        context={context}
        initialMessages={initialMessages}
        onMessagesChange={onMessagesChange}
      />
    </div>
  )

  if (pipWindow) {
    return createPortal(
      <div className="flex flex-col h-screen bg-gray-950">
        {header}
        {body}
      </div>,
      pipWindow.document.body,
    )
  }

  return (
    <div
      className="fixed z-50 flex flex-col bg-gray-950 rounded-lg overflow-hidden shadow-2xl border border-gray-700"
      style={{ left: pos.x, top: pos.y, width: size.width, height: size.height }}
    >
      {header}
      {body}
      <div
        onMouseDown={startResize}
        title="Resize"
        className="absolute bottom-0 right-0 w-4 h-4 cursor-nwse-resize"
      >
        <div className="absolute bottom-0.5 right-0.5 w-2.5 h-2.5 border-b-2 border-r-2 border-gray-600 rounded-br-sm" />
      </div>
    </div>
  )
}
