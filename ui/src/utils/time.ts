/**
 * Centralized time formatting.
 *
 * Every timestamp shown in the UI passes through these helpers so the entire
 * application uses one consistent timezone — the one configured in
 * system.json5 as `ui_utc` (default UTC+3, the broker's timezone).
 *
 * Stored timestamps in the database carry their original timezone (broker
 * candles are UTC+3, locally-set timestamps are UTC). The formatters here
 * normalize all of them to the configured UI timezone at display time.
 */

let UI_UTC_OFFSET_HOURS = 3   // fallback until /system/ui-settings has been fetched

export function setUiUtcOffset(hours: number): void {
  if (Number.isFinite(hours)) UI_UTC_OFFSET_HOURS = hours
}

export function getUiUtcOffset(): number {
  return UI_UTC_OFFSET_HOURS
}

/**
 * Convert a JS Date to a Date whose UTC fields equal the wall-clock values
 * of the configured UI timezone. Used to extract hour/minute/etc. without
 * relying on the browser's local timezone.
 */
function toUiClock(date: Date): Date {
  return new Date(date.getTime() + UI_UTC_OFFSET_HOURS * 3_600_000)
}

function pad2(n: number): string {
  return n < 10 ? `0${n}` : String(n)
}

const TZ_LABEL = () => {
  const h = UI_UTC_OFFSET_HOURS
  const sign = h >= 0 ? '+' : '-'
  return `UTC${sign}${Math.abs(h)}`
}

/** "23:50" */
export function formatHM(input: Date | number | string | null | undefined): string {
  if (input == null) return '-'
  const date = typeof input === 'number'
    ? new Date(input * 1000)                  // unix seconds (lightweight-charts)
    : typeof input === 'string'
      ? new Date(input)
      : input
  if (isNaN(date.getTime())) return '-'
  const ui = toUiClock(date)
  return `${pad2(ui.getUTCHours())}:${pad2(ui.getUTCMinutes())}`
}

/** "2026-06-05 23:50:00 UTC+3" */
export function formatTs(input: string | Date | null | undefined, withTz = true): string {
  if (input == null || input === '') return '-'
  const date = typeof input === 'string' ? new Date(input) : input
  if (isNaN(date.getTime())) return '-'
  const ui = toUiClock(date)
  const y = ui.getUTCFullYear()
  const mo = pad2(ui.getUTCMonth() + 1)
  const d = pad2(ui.getUTCDate())
  const h = pad2(ui.getUTCHours())
  const mi = pad2(ui.getUTCMinutes())
  const s = pad2(ui.getUTCSeconds())
  const base = `${y}-${mo}-${d} ${h}:${mi}:${s}`
  return withTz ? `${base} ${TZ_LABEL()}` : base
}

/** "23:50" — accepts unix seconds (used by lightweight-charts tickMarkFormatter) */
export function formatChartHM(unixSeconds: number): string {
  const ui = toUiClock(new Date(unixSeconds * 1000))
  return `${pad2(ui.getUTCHours())}:${pad2(ui.getUTCMinutes())}`
}

/** Fetch the UI timezone from the server. Call once at app startup. */
export async function loadUiSettings(): Promise<void> {
  try {
    const res = await fetch('/system/ui-settings')
    if (!res.ok) return
    const data = await res.json() as { ui_utc?: number }
    if (typeof data.ui_utc === 'number') setUiUtcOffset(data.ui_utc)
  } catch {
    // keep default
  }
}
