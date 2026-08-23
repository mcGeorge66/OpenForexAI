/**
 * Wraps the Document Picture-in-Picture API (Chrome/Edge 116+ only, requires a secure
 * context — HTTPS or localhost) so any of the app's floating draggable windows
 * (ChartAssistantWindow, OrderInvestigateModal, EventDetailWindow, PromptEditorWindow)
 * can be "popped out" into a real, separate OS-level window that can be dragged outside
 * the browser entirely — not just moved within the page's own viewport like the existing
 * custom drag/resize chrome allows.
 *
 * Deliberately just a hook (logic only), not a shared chrome component: the four windows
 * that use this have different headers/content/resize strategies, and forcing them into
 * one generic wrapper would be a worse abstraction than each keeping its own JSX and
 * adding a pop-out button + a conditional portal render.
 *
 * Crucially, the returned window runs in the SAME JavaScript context as the opener (unlike
 * window.open()) — no cross-window messaging or state duplication needed. A caller just
 * renders its existing React tree into pipWindow.document.body via createPortal once
 * pipWindow is set, and every hook/handler keeps working exactly as before.
 */
import { useCallback, useEffect, useState } from 'react'

interface DocumentPictureInPictureAPI {
  requestWindow(options?: { width?: number; height?: number }): Promise<Window>
  window: Window | null
}

declare global {
  interface Window {
    documentPictureInPicture?: DocumentPictureInPictureAPI
  }
}

export function isPictureInPictureSupported(): boolean {
  return typeof window !== 'undefined' && 'documentPictureInPicture' in window
}

// The PiP window starts with a blank document — copy every stylesheet from the opener so
// Tailwind classes actually render instead of showing unstyled HTML.
function copyStylesInto(target: Document) {
  for (const sheet of Array.from(document.styleSheets)) {
    try {
      const owner = sheet.ownerNode
      if (owner instanceof HTMLLinkElement) {
        const link = target.createElement('link')
        link.rel = 'stylesheet'
        link.href = owner.href
        target.head.appendChild(link)
      } else if (owner instanceof HTMLStyleElement) {
        target.head.appendChild(owner.cloneNode(true))
      }
    } catch {
      // Cross-origin stylesheet — can't introspect its ownerNode, skip it.
    }
  }
}

export interface UseDocumentPictureInPictureOptions {
  width?: number
  height?: number
}

// Deliberately has NO "the feature is now fully closed" callback: ending Picture-in-Picture
// (by any means — the redock button, or the OS window's own close chrome) only ever means
// "stop floating in a separate OS window, go back to rendering in the page" — the same way
// closing a video's PiP mini-player just resumes it inline, it doesn't stop playback.
// Fully closing the underlying feature (e.g. the whole Chart Assistant) stays a completely
// separate action the caller wires to its own close button, only reachable once redocked.
export function useDocumentPictureInPicture(options: UseDocumentPictureInPictureOptions = {}) {
  const { width = 420, height = 560 } = options
  const [pipWindow, setPipWindow] = useState<Window | null>(null)

  const open = useCallback(async () => {
    if (!isPictureInPictureSupported() || pipWindow) return
    try {
      const pip = await window.documentPictureInPicture!.requestWindow({ width, height })
      copyStylesInto(pip.document)
      pip.document.body.style.margin = '0'
      pip.document.body.style.background = 'transparent'
      pip.addEventListener('pagehide', () => setPipWindow(null), { once: true })
      setPipWindow(pip)
    } catch (err) {
      // Most commonly: called without a fresh user gesture (browser requirement) —
      // nothing to recover from here, just don't leave an unhandled rejection.
      console.warn('Document Picture-in-Picture request failed:', err)
    }
  }, [width, height, pipWindow])

  // Redocks — ends PiP, falls back to normal in-page rendering. Never closes the feature.
  const close = useCallback(() => {
    pipWindow?.close()
    setPipWindow(null)
  }, [pipWindow])

  // If the component that owns this hook unmounts while popped out (e.g. the user
  // navigates away in the main tab), don't leave an orphaned window with dead React
  // state behind — close it too.
  useEffect(() => {
    return () => { pipWindow?.close() }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pipWindow])

  return { pipWindow, open, close, supported: isPictureInPictureSupported() }
}
