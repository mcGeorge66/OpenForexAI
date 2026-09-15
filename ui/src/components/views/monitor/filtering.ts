import type { MonitoringEvent } from '@/api/client'

export type MonitorFilterField =
  | 'event_type'
  | 'source'
  | 'broker'
  | 'pair'
  | 'sender'
  | 'target'
  | 'message_id'
  | 'correlation_id'
  | 'payload'

export type MonitorFilterOperator =
  | 'equals'
  | 'contains'
  | 'starts_with'
  | 'ends_with'
  | 'exists'

export type MonitorFilterJoin = 'START' | 'AND' | 'AND_NOT' | 'OR' | 'OR_NOT'

export type MonitorFilterRule = {
  id: string
  join: MonitorFilterJoin
  field: MonitorFilterField
  operator: MonitorFilterOperator
  value: string
  path?: string
}

export type MonitorFilterGroup = {
  rules: MonitorFilterRule[]
}

export type SavedMonitorFilter = {
  id: string
  name: string
  definition: MonitorFilterGroup
  options: {
    includeResponses: boolean
    showOrphans: boolean
    /** Send matching events to Telegram, so the filter keeps working when
     *  nobody has the console open. Translated into a notification rule on
     *  save — see compileFilterForNotification. */
    notify?: boolean
  }
}

export const FILTER_FIELDS: Array<{ value: MonitorFilterField; label: string }> = [
  { value: 'event_type', label: 'Event Type' },
  { value: 'source', label: 'Source' },
  { value: 'broker', label: 'Broker' },
  { value: 'pair', label: 'Pair' },
  { value: 'sender', label: 'Sender' },
  { value: 'target', label: 'Target' },
  { value: 'message_id', label: 'Message ID' },
  { value: 'correlation_id', label: 'Correlation ID' },
  { value: 'payload', label: 'Payload Field' },
]

export const FILTER_OPERATORS: Array<{ value: MonitorFilterOperator; label: string }> = [
  { value: 'contains', label: 'contains' },
  { value: 'equals', label: 'equals' },
  { value: 'starts_with', label: 'starts with' },
  { value: 'ends_with', label: 'ends with' },
  { value: 'exists', label: 'exists' },
]

export function createFilterRule(): MonitorFilterRule {
  return {
    id: makeId(),
    join: 'START',
    field: 'event_type',
    operator: 'contains',
    value: '',
  }
}

export function createFilterGroup(): MonitorFilterGroup {
  return {
    rules: [],
  }
}

export function cloneFilterGroup(group: MonitorFilterGroup): MonitorFilterGroup {
  return {
    rules: group.rules.map(rule => ({ ...rule })),
  }
}

export function isPrimaryEvent(event: MonitoringEvent): boolean {
  return payloadString(event.payload, 'correlation_id') === null
}

export function matchesFilterGroup(group: MonitorFilterGroup, event: MonitoringEvent): boolean {
  if (group.rules.length === 0) return true

  let result = false
  group.rules.forEach((rule, index) => {
    const matched = matchesRule(rule, event)
    const join = index === 0 ? 'START' : (rule.join ?? 'AND')
    if (join === 'START') {
      result = matched
      return
    }
    if (join === 'AND') {
      result = result && matched
      return
    }
    if (join === 'AND_NOT') {
      result = result && !matched
      return
    }
    if (join === 'OR') {
      result = result || matched
      return
    }
    result = result || !matched
  })
  return result
}

function matchesRule(rule: MonitorFilterRule, event: MonitoringEvent): boolean {
  const raw = ruleValue(rule, event)
  if (rule.operator === 'exists') return hasValue(raw)

  const left = normaliseValue(raw)
  const right = rule.value.trim().toLowerCase()
  if (!right) return true

  if (rule.operator === 'equals') return left === right
  if (rule.operator === 'starts_with') return left.startsWith(right)
  if (rule.operator === 'ends_with') return left.endsWith(right)
  return left.includes(right)
}

function ruleValue(rule: MonitorFilterRule, event: MonitoringEvent): unknown {
  switch (rule.field) {
    case 'event_type':
      return event.event_type
    case 'source':
      return event.source
    case 'broker':
      return event.broker
    case 'pair':
      return event.pair
    case 'sender':
      return payloadString(event.payload, 'sender')
    case 'target':
      return payloadTarget(event.payload)
    case 'message_id':
      return payloadString(event.payload, 'message_id')
    case 'correlation_id':
      return payloadString(event.payload, 'correlation_id')
    case 'payload':
      return nestedValue(event.payload, rule.path)
    default:
      return null
  }
}

function payloadString(payload: Record<string, unknown>, key: string): string | null {
  const value = payload[key]
  return typeof value === 'string' && value.trim() ? value : null
}

function payloadTarget(payload: Record<string, unknown>): string | null {
  const value = payload.target
  if (typeof value === 'string' && value.trim()) return value
  if (Array.isArray(value)) return value.filter(item => typeof item === 'string').join(', ')
  return null
}

function nestedValue(value: unknown, path: string | undefined): unknown {
  if (!path?.trim()) return value
  const parts = path.split('.').map(part => part.trim()).filter(Boolean)
  let current: unknown = value
  for (const part of parts) {
    if (!current || typeof current !== 'object' || Array.isArray(current)) return null
    current = (current as Record<string, unknown>)[part]
  }
  return current
}

function hasValue(value: unknown): boolean {
  if (value === null || value === undefined) return false
  if (typeof value === 'string') return value.trim().length > 0
  if (Array.isArray(value)) return value.length > 0
  if (typeof value === 'object') return Object.keys(value as Record<string, unknown>).length > 0
  return true
}

function normaliseValue(value: unknown): string {
  if (value === null || value === undefined) return ''
  if (typeof value === 'string') return value.toLowerCase()
  if (typeof value === 'number' || typeof value === 'boolean') return String(value).toLowerCase()
  return JSON.stringify(value).toLowerCase()
}

function makeId(): string {
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`
}

// ── Forwarding a filter to Telegram ──────────────────────────────────────────
//
// A saved filter can be marked "send matches to Telegram". Rather than teaching
// the backend a second filter language, the filter is *translated* here into
// the condition format the notification rules already use — so there is one
// evaluator, in Python, and nothing to drift.
//
// The monitoring events reach the bus through the alert bridge, which flattens
// them into a payload carrying alert_type / source / broker / pair plus the
// original fields. Those are the names a translated condition refers to.

/** Field name in the console → key in the bridged system_alert payload. */
const FIELD_TO_PAYLOAD_KEY: Partial<Record<MonitorFilterField, string>> = {
  event_type: 'alert_type',
  source: 'source',
  broker: 'broker',
  pair: 'pair',
  sender: 'sender',
  target: 'target',
  message_id: 'message_id',
  correlation_id: 'correlation_id',
}

export type CompiledFilter =
  | { ok: true; onlyIf: Record<string, unknown>; alertTypes: string[] }
  | { ok: false; reason: string }

function escapeForRegex(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

function conditionFor(rule: MonitorFilterRule, negated: boolean): unknown | null {
  const value = rule.value.trim()
  if (rule.operator === 'exists') return { exists: !negated }
  if (!value) return null
  if (negated) {
    // Only equality has a direct negation in the rule engine; the others
    // would need a "not contains" that does not exist, and inventing one
    // silently would change what the filter means.
    return rule.operator === 'equals' ? { ne: value } : null
  }
  if (rule.operator === 'equals') return value
  if (rule.operator === 'contains') return { contains: value }
  if (rule.operator === 'starts_with') return { regex: `^${escapeForRegex(value)}` }
  if (rule.operator === 'ends_with') return { regex: `${escapeForRegex(value)}$` }
  return null
}

/** Translate a saved filter into notification-rule conditions. */
export function compileFilterForNotification(group: MonitorFilterGroup): CompiledFilter {
  if (group.rules.length === 0) {
    return { ok: false, reason: 'The filter is empty — it would report every event.' }
  }

  const onlyIf: Record<string, unknown> = {}
  const alertTypes: string[] = []

  for (let i = 0; i < group.rules.length; i++) {
    const rule = group.rules[i]
    const join = i === 0 ? 'START' : (rule.join ?? 'AND')
    if (join === 'OR' || join === 'OR_NOT') {
      return {
        ok: false,
        reason: 'OR conditions cannot be translated — '
          + 'notification rules combine conditions with AND only. '
          + 'Create two filters instead.',
      }
    }

    const key = rule.field === 'payload'
      ? (rule.path ?? '').trim()
      : FIELD_TO_PAYLOAD_KEY[rule.field]
    if (!key) {
      return { ok: false, reason: `The field "${rule.field}" has no counterpart in the message.` }
    }

    const condition = conditionFor(rule, join === 'AND_NOT')
    if (condition === null) {
      return {
        ok: false,
        reason: join === 'AND_NOT'
          ? `"${rule.operator}" cannot be negated — only "equals" can be.`
          : `The condition for "${rule.field}" is incomplete.`,
      }
    }
    if (key in onlyIf) {
      return {
        ok: false,
        reason: `Two conditions on "${key}" — a rule can check only one per field.`,
      }
    }
    onlyIf[key] = condition
    if (key === 'alert_type' && typeof condition === 'string') alertTypes.push(condition)
  }

  if (alertTypes.length === 0) {
    return {
      ok: false,
      reason: 'Without "event type equals …" the bridge does not know which '
        + 'Monitoring-Ereignisse sie weiterleiten soll.',
    }
  }
  return { ok: true, onlyIf, alertTypes }
}
