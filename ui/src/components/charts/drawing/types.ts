import type { LineStyle, UTCTimestamp } from 'lightweight-charts'

export interface DrawingPoint {
  price: number
  time: UTCTimestamp
}

export interface DrawingStyle {
  color: string
  lineStyle: LineStyle
  lineWidth: number
  fillColor?: string
  fillOpacity?: number
  fontSize?: number
}

export type DrawingToolName =
  | 'hline'
  | 'vline'
  | 'ray'
  | 'extended_line'
  | 'trendline'
  | 'channel'
  | 'rect'
  | 'textlabel'
  | 'arrow_up'
  | 'arrow_down'
  | 'fib_ret'
  | 'fib_ext'
  | 'fib_fan'
  | 'fib_timezones'
  | 'pitchfork'
  | 'elliott'
  | 'measure'

export interface Drawing {
  id: string
  tool: DrawingToolName
  points: DrawingPoint[]
  style: DrawingStyle
  label?: string
  elliottLabels?: string[]
  visible: boolean
  selected: boolean
}

export const REQUIRED_POINTS: Record<DrawingToolName, number | null> = {
  hline: 1,
  vline: 1,
  ray: 1,
  extended_line: 2,
  trendline: 2,
  channel: 3,
  rect: 2,
  textlabel: 1,
  arrow_up: 1,
  arrow_down: 1,
  fib_ret: 2,
  fib_ext: 3,
  fib_fan: 2,
  fib_timezones: 2,
  pitchfork: 3,
  elliott: null,
  measure: 2,
}

export const TOOL_LABELS: Record<DrawingToolName, string> = {
  hline: 'H Line',
  vline: 'V Line',
  ray: 'Ray',
  extended_line: 'Ext. Line',
  trendline: 'Trend Line',
  channel: 'Channel',
  rect: 'Rectangle',
  textlabel: 'Label',
  arrow_up: '▲ Up',
  arrow_down: '▼ Down',
  fib_ret: 'Fib Ret.',
  fib_ext: 'Fib Ext.',
  fib_fan: 'Fib Fan',
  fib_timezones: 'Fib TZ',
  pitchfork: 'Pitchfork',
  elliott: 'Elliott',
  measure: '↔ Measure',
}
