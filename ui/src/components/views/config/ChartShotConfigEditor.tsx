import { useEffect, useState } from 'react'
import { ChevronDown, ChevronRight, MessageSquare, Plus, RefreshCw, Save, Trash2, Play } from 'lucide-react'
import { api } from '@/api/client'
import { AiAssistantModal } from '@/components/common/AiAssistantModal'

// ─── Types ────────────────────────────────────────────────────────────────────

type OutputMode  = 'temp' | 'keep'
type ChartStyle  = 'dark' | 'light'
type IndicatorName = 'EMA' | 'SMA' | 'RSI' | 'ATR' | 'BB' | 'VWAP' | 'SLOPE_E' | 'SLOPE_S'
type PriceSource = 'HL' | 'OC'
type SortBy      = 'nearest' | 'prominent'

interface IndicatorConfig {
  id:           string
  name:         IndicatorName
  period:       number
  timeframe:    string
  color:        string
  line_style:   number   // 0=Solid 1=Dashed 2=LargeDashed 3=Dotted 4=SparseDotted
  line_width:   number
  visible:      boolean
  smooth_period?: number // for SLOPE_E / SLOPE_S
}

interface SwingConfig {
  enabled:      boolean
  timeframe:    string
  count:        number
  atr_period:   number
  min_gap_atr:  number
  line_width:   number
  line_style:   number
  price_source: PriceSource
  sort_by:      SortBy
}

interface ChartShotNamedConfig {
  output_mode:  OutputMode
  style:        ChartStyle
  description:  string
  indicators:   IndicatorConfig[]
  swing_levels: SwingConfig
}

interface ChartShotRoot {
  output_dir: string
  configs:    Record<string, ChartShotNamedConfig>
}

interface AgentCfg {
  agent_id: string
  pair:   string | null
  broker: string | null
}

// ─── Constants ────────────────────────────────────────────────────────────────

const TIMEFRAMES = ['M5', 'M15', 'M30', 'H1', 'H4', 'D1'] as const

const INDICATOR_DEFS: Array<{ name: IndicatorName; label: string; defaultPeriod: number }> = [
  { name: 'EMA',    label: 'EMA',    defaultPeriod: 20 },
  { name: 'SMA',    label: 'SMA',    defaultPeriod: 20 },
  { name: 'RSI',    label: 'RSI',    defaultPeriod: 14 },
  { name: 'ATR',    label: 'ATR',    defaultPeriod: 14 },
  { name: 'BB',     label: 'BB',     defaultPeriod: 20 },
  { name: 'VWAP',   label: 'VWAP',   defaultPeriod: 0  },
  { name: 'SLOPE_E', label: 'SlopeE', defaultPeriod: 20 },
  { name: 'SLOPE_S', label: 'SlopeS', defaultPeriod: 20 },
]

const LINE_STYLE_OPTS = [
  { value: 0, label: 'Solid'       },
  { value: 1, label: 'Dashed'      },
  { value: 2, label: 'LargeDashed' },
  { value: 3, label: 'Dotted'      },
  { value: 4, label: 'SparseDotted'},
]

const DEFAULT_COLORS = ['#10b981','#3b82f6','#f59e0b','#ef4444','#8b5cf6','#ec4899','#06b6d4','#84cc16']

const DEFAULT_SWING: SwingConfig = {
  enabled: false, timeframe: 'H1', count: 5, atr_period: 14,
  min_gap_atr: 0.3, line_width: 2, line_style: 1,
  price_source: 'HL', sort_by: 'nearest',
}

const DEFAULT_NAMED: ChartShotNamedConfig = {
  output_mode: 'temp', style: 'dark', description: '', indicators: [], swing_levels: { ...DEFAULT_SWING },
}

const DEFAULT_ROOT: ChartShotRoot = {
  output_dir: 'data/chartshots',
  configs: { default: { ...DEFAULT_NAMED } },
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

let _uidCounter = 0
function uid() { return `ind_${Date.now()}_${++_uidCounter}` }

function normalizeIndicator(v: unknown): IndicatorConfig | null {
  if (!v || typeof v !== 'object') return null
  const c = v as Record<string, unknown>
  const name = c.name as string
  if (!['EMA','SMA','RSI','ATR','BB','VWAP','SLOPE_E','SLOPE_S'].includes(name)) return null
  return {
    id:         typeof c.id === 'string' ? c.id : uid(),
    name:       name as IndicatorName,
    period:     typeof c.period === 'number' ? c.period : 20,
    timeframe:  typeof c.timeframe === 'string' ? c.timeframe : 'M15',
    color:      typeof c.color === 'string' ? c.color : '#10b981',
    line_style: typeof c.line_style === 'number' ? c.line_style : 0,
    line_width: typeof c.line_width === 'number' ? c.line_width : 1,
    visible:    c.visible !== false,
    ...(typeof c.smooth_period === 'number' ? { smooth_period: c.smooth_period } : {}),
  }
}

function normalizeSwing(v: unknown): SwingConfig {
  if (!v || typeof v !== 'object') return { ...DEFAULT_SWING }
  const c = v as Record<string, unknown>
  return {
    enabled:      c.enabled === true,
    timeframe:    typeof c.timeframe === 'string' ? c.timeframe : DEFAULT_SWING.timeframe,
    count:        typeof c.count === 'number' ? c.count : DEFAULT_SWING.count,
    atr_period:   typeof c.atr_period === 'number' ? c.atr_period : DEFAULT_SWING.atr_period,
    min_gap_atr:  typeof c.min_gap_atr === 'number' ? c.min_gap_atr : DEFAULT_SWING.min_gap_atr,
    line_width:   typeof c.line_width === 'number' ? c.line_width : DEFAULT_SWING.line_width,
    line_style:   typeof c.line_style === 'number' ? c.line_style : DEFAULT_SWING.line_style,
    price_source: c.price_source === 'OC' ? 'OC' : 'HL',
    sort_by:      c.sort_by === 'prominent' ? 'prominent' : 'nearest',
  }
}

function normalizeRoot(raw: unknown): ChartShotRoot {
  if (!raw || typeof raw !== 'object') return { ...DEFAULT_ROOT, configs: { default: { ...DEFAULT_NAMED } } }
  const r = raw as Record<string, unknown>
  const output_dir = typeof r.output_dir === 'string' ? r.output_dir : 'data/chartshots'
  const rawConfigs = r.configs && typeof r.configs === 'object' ? r.configs as Record<string, unknown> : {}
  const configs: Record<string, ChartShotNamedConfig> = {}
  for (const [k, v] of Object.entries(rawConfigs)) {
    if (!v || typeof v !== 'object') continue
    const c = v as Record<string, unknown>
    configs[k] = {
      output_mode:  (['temp','keep'].includes(c.output_mode as string) ? c.output_mode as OutputMode : 'temp'),
      style:        (c.style === 'light' ? 'light' : 'dark'),
      description:  typeof c.description === 'string' ? c.description : '',
      indicators:   Array.isArray(c.indicators)
        ? c.indicators.map(normalizeIndicator).filter(Boolean) as IndicatorConfig[]
        : [],
      swing_levels: normalizeSwing(c.swing_levels),
    }
  }
  if (!configs.default) configs.default = { ...DEFAULT_NAMED }
  return { output_dir, configs }
}

function extractAgents(configView: Record<string, unknown>): AgentCfg[] {
  const agents = configView.agents
  if (!agents || typeof agents !== 'object') return []
  return Object.entries(agents as Record<string, unknown>)
    .filter(([, v]) => v && typeof v === 'object')
    .map(([agent_id, v]) => {
      const c = v as Record<string, unknown>
      return { agent_id, pair: typeof c.pair === 'string' ? c.pair : null, broker: typeof c.broker === 'string' ? c.broker : null }
    })
    .filter(a => a.pair && a.broker)
}

// ─── Component ────────────────────────────────────────────────────────────────

export function ChartShotConfigEditor() {
  const [root, setRoot]             = useState<ChartShotRoot>(DEFAULT_ROOT)
  const [selected, setSelected]     = useState<string>('default')
  const [newName, setNewName]       = useState('')
  const [loading, setLoading]       = useState(false)
  const [saving, setSaving]         = useState(false)
  const [dirty, setDirty]           = useState(false)
  const [message, setMessage]       = useState<{ text: string; ok: boolean } | null>(null)
  const [aiAssistantOpen, setAiAssistantOpen] = useState(false)

  // Preview state
  const [previewOpen, setPreviewOpen] = useState(true)
  const [agents, setAgents]         = useState<AgentCfg[]>([])
  const [selAgent, setSelAgent]     = useState('')
  const [broker, setBroker]         = useState('')
  const [pair, setPair]             = useState('')
  const [timeframe, setTimeframe]   = useState<string>('M15')
  const [candles, setCandles]       = useState(100)
  const [running, setRunning]           = useState(false)
  const [previewUrl, setPreviewUrl]     = useState<string | null>(null)
  const [previewFilename, setPreviewFilename] = useState<string | null>(null)
  const [runError, setRunError]         = useState<string | null>(null)

  // ── Load ──────────────────────────────────────────────────────────────────

  const load = async () => {
    setLoading(true)
    setMessage(null)
    try {
      const [sys, cfg] = await Promise.all([api.getSystemConfig(), api.getConfigView()])
      const cs = (sys as Record<string, unknown>).chartshot
      const normalized = normalizeRoot(cs)
      setRoot(normalized)
      if (!normalized.configs[selected]) setSelected(Object.keys(normalized.configs)[0] ?? 'default')
      const agentList = extractAgents(cfg)
      setAgents(agentList)
      if (agentList.length > 0 && !selAgent) {
        const first = agentList[0]
        setSelAgent(first.agent_id)
        setBroker(first.broker ?? '')
        setPair(first.pair ?? '')
      }
      setDirty(false)
    } catch (e) {
      setMessage({ text: String(e), ok: false })
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { void load() }, [])  // eslint-disable-line react-hooks/exhaustive-deps

  // ── Agent selection ───────────────────────────────────────────────────────

  const onSelectAgent = (agentId: string) => {
    setSelAgent(agentId)
    const a = agents.find(x => x.agent_id === agentId)
    if (a) { setBroker(a.broker ?? ''); setPair(a.pair ?? '') }
  }

  // ── Run preview ───────────────────────────────────────────────────────────

  const runPreview = async () => {
    setRunning(true)
    setRunError(null)
    setPreviewUrl(null)
    setPreviewFilename(null)
    const current = root.configs[selected] ?? DEFAULT_NAMED
    try {
      const resp = await api.executeTool(
        'chartshot',
        {
          timeframe,
          candles,
          config: selected,
          _indicators_override: current.indicators,
          _swing_levels_override: current.swing_levels,
          _description_override: current.description,
        },
        null,
        broker || null,
        null,
        pair || null,
      )
      if (resp.is_error) {
        const res = resp.result as Record<string, unknown> | string | null
        const msg = typeof res === 'string' ? res
          : res && typeof res === 'object' && typeof res.error === 'string' ? res.error
          : JSON.stringify(res)
        setRunError(msg)
        return
      }
      const result = resp.result as Record<string, unknown>
      const filePath = result.file_path as string | undefined
      if (filePath) {
        const filename = filePath.replace(/\\/g, '/').split('/').pop() ?? ''
        setPreviewFilename(filename)
        setPreviewUrl(`/chartshots/${encodeURIComponent(filename)}?t=${Date.now()}`)
      } else {
        setRunError('No file_path in tool result')
      }
    } catch (e) {
      setRunError(String(e))
    } finally {
      setRunning(false)
    }
  }

  // ── Save ──────────────────────────────────────────────────────────────────

  const save = async () => {
    setSaving(true)
    setMessage(null)
    try {
      const sys = await api.getSystemConfig() as Record<string, unknown>
      await api.saveSystemConfig({ ...sys, chartshot: root })
      setDirty(false)
      setMessage({ text: 'Saved.', ok: true })
    } catch (e) {
      setMessage({ text: String(e), ok: false })
    } finally {
      setSaving(false)
    }
  }

  // ── Mutations ─────────────────────────────────────────────────────────────

  const updateOutputDir = (v: string) => { setRoot(r => ({ ...r, output_dir: v })); setDirty(true) }

  const updateSelected = (field: keyof ChartShotNamedConfig, value: unknown) => {
    setRoot(r => ({ ...r, configs: { ...r.configs, [selected]: { ...r.configs[selected], [field]: value } } }))
    setDirty(true)
  }

  const addConfig = () => {
    const name = newName.trim().toLowerCase().replace(/\s+/g, '_')
    if (!name || root.configs[name]) return
    setRoot(r => ({ ...r, configs: { ...r.configs, [name]: { ...DEFAULT_NAMED } } }))
    setSelected(name)
    setNewName('')
    setDirty(true)
  }

  const deleteSelected = () => {
    if (selected === 'default') return
    const next = { ...root.configs }
    delete next[selected]
    setRoot(r => ({ ...r, configs: next }))
    setSelected('default')
    setDirty(true)
  }

  // ── Indicator mutations ───────────────────────────────────────────────────

  const addIndicator = (name: IndicatorName) => {
    const def  = INDICATOR_DEFS.find(d => d.name === name)!
    const cur  = root.configs[selected] ?? DEFAULT_NAMED
    const newInd: IndicatorConfig = {
      id:         uid(),
      name,
      period:     def.defaultPeriod,
      timeframe:  'M15',
      color:      DEFAULT_COLORS[cur.indicators.length % DEFAULT_COLORS.length],
      line_style: 0,
      line_width: 1,
      visible:    true,
      ...(['SLOPE_E','SLOPE_S'].includes(name) ? { smooth_period: 3 } : {}),
    }
    updateSelected('indicators', [...cur.indicators, newInd])
  }

  const removeIndicator = (id: string) => {
    const cur = root.configs[selected] ?? DEFAULT_NAMED
    updateSelected('indicators', cur.indicators.filter(i => i.id !== id))
  }

  const updateIndicator = (id: string, patch: Partial<IndicatorConfig>) => {
    const cur = root.configs[selected] ?? DEFAULT_NAMED
    updateSelected('indicators', cur.indicators.map(i => i.id === id ? { ...i, ...patch } : i))
  }

  // ── Swing mutations ───────────────────────────────────────────────────────

  const updateSwing = (patch: Partial<SwingConfig>) => {
    const cur = root.configs[selected] ?? DEFAULT_NAMED
    updateSelected('swing_levels', { ...cur.swing_levels, ...patch })
  }

  const current = root.configs[selected] ?? DEFAULT_NAMED

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <>
      <div className="flex flex-col h-full min-h-0 text-sm">

      {/* Header */}
      <div className="flex-shrink-0 flex items-center justify-between gap-2 px-4 py-3 border-b border-gray-700 bg-gray-900">
        <div>
          <h2 className="text-base font-semibold text-gray-100">Chartshot Config</h2>
          <p className="text-xs text-white mt-0.5">config/system.json5 → chartshot</p>
        </div>
        <div className="flex items-center gap-2">
          {message && (
            <span className={`text-xs ${message.ok ? 'text-emerald-400' : 'text-red-400'}`}>{message.text}</span>
          )}
          <button
            type="button"
            onClick={() => setAiAssistantOpen(true)}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded bg-indigo-700 hover:bg-indigo-600 text-white text-xs font-medium transition-colors border border-indigo-500/40"
            title="AI Assistant"
          >
            <MessageSquare className="w-3.5 h-3.5" />
            AI Assistant
          </button>
          <button
            type="button" onClick={() => void load()} disabled={loading}
            className="p-1.5 rounded text-gray-400 hover:text-gray-200 hover:bg-gray-700 transition-colors" title="Reload"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          </button>
          <button
            type="button" onClick={() => void save()} disabled={saving || !dirty}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded bg-blue-600 hover:bg-blue-500 disabled:opacity-40 text-white text-xs font-medium transition-colors"
          >
            <Save className="w-3.5 h-3.5" />
            {saving ? 'Saving…' : 'Save'}
          </button>
        </div>
      </div>

      <div className="flex flex-1 min-h-0 overflow-hidden">

        {/* Left — config list */}
        <div className="w-52 flex-shrink-0 flex flex-col border-r border-gray-700 bg-gray-900">
          <div className="px-3 py-3 border-b border-gray-700/60">
            <label className="block text-xs text-white mb-1">Output directory</label>
            <input
              type="text" value={root.output_dir} onChange={e => updateOutputDir(e.target.value)}
              className="w-full bg-gray-800 border border-gray-600 rounded px-2 py-1 text-xs text-gray-200 focus:outline-none focus:border-gray-400"
            />
          </div>
          <div className="flex-1 overflow-y-auto py-1">
            {Object.keys(root.configs).map(name => (
              <button
                key={name} type="button" onClick={() => setSelected(name)}
                className={`w-full text-left px-3 py-2 text-xs transition-colors ${
                  name === selected ? 'bg-blue-700/30 text-blue-300 font-medium' : 'text-gray-300 hover:bg-gray-800'
                }`}
              >
                {name}
                {name === 'default' && <span className="ml-1.5 text-[10px] text-white">(default)</span>}
              </button>
            ))}
          </div>
          <div className="flex-shrink-0 px-3 py-2 border-t border-gray-700 flex items-center gap-1">
            <input
              type="text" value={newName} onChange={e => setNewName(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && addConfig()}
              placeholder="new config name"
              className="flex-1 bg-gray-800 border border-gray-600 rounded px-2 py-1 text-xs text-gray-200 placeholder-gray-600 focus:outline-none focus:border-gray-400 min-w-0"
            />
            <button
              type="button" onClick={addConfig} disabled={!newName.trim()}
              className="p-1 rounded text-gray-400 hover:text-gray-200 hover:bg-gray-700 disabled:opacity-30 transition-colors flex-shrink-0" title="Add config"
            >
              <Plus className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>

        {/* Right — editor + preview */}
        <div className="flex-1 overflow-y-auto px-6 py-5 space-y-6">

          {/* ── Preview ─────────────────────────────────────────────────── */}
          <div className="rounded border border-gray-700 bg-gray-800/40 overflow-hidden">
            <button
              type="button"
              onClick={() => setPreviewOpen(v => !v)}
              className="w-full flex items-center justify-between px-4 py-2.5 border-b border-gray-700 bg-gray-800/60 hover:bg-gray-700/60 transition-colors text-left"
            >
              <h3 className="text-xs font-semibold text-gray-300 uppercase tracking-wider">Preview</h3>
              {previewOpen
                ? <ChevronDown className="w-3.5 h-3.5 text-gray-500" />
                : <ChevronRight className="w-3.5 h-3.5 text-gray-500" />
              }
            </button>
            {previewOpen && (
              <div className="px-4 py-4 space-y-3">
                {/* Controls */}
                <div className="grid grid-cols-2 gap-3">
                  <div className="col-span-2">
                    <label className="block text-xs text-white mb-1">Agent</label>
                    <select
                      value={selAgent} onChange={e => onSelectAgent(e.target.value)}
                      className="w-full bg-gray-800 border border-gray-600 rounded px-2 py-1.5 text-xs text-gray-200 focus:outline-none focus:border-gray-400"
                    >
                      <option value="">— select agent —</option>
                      {agents.map(a => <option key={a.agent_id} value={a.agent_id}>{a.agent_id}</option>)}
                    </select>
                  </div>
                  <div>
                    <label className="block text-xs text-white mb-1">Broker</label>
                    <input
                      type="text" value={broker} onChange={e => setBroker(e.target.value)} placeholder="broker name"
                      className="w-full bg-gray-800 border border-gray-600 rounded px-2 py-1.5 text-xs text-gray-200 focus:outline-none focus:border-gray-400"
                    />
                  </div>
                  <div>
                    <label className="block text-xs text-white mb-1">Pair</label>
                    <input
                      type="text" value={pair} onChange={e => setPair(e.target.value.toUpperCase())} placeholder="EURUSD"
                      className="w-full bg-gray-800 border border-gray-600 rounded px-2 py-1.5 text-xs text-gray-200 focus:outline-none focus:border-gray-400"
                    />
                  </div>
                  <div>
                    <label className="block text-xs text-white mb-1">Timeframe</label>
                    <select
                      value={timeframe} onChange={e => setTimeframe(e.target.value)}
                      className="w-full bg-gray-800 border border-gray-600 rounded px-2 py-1.5 text-xs text-gray-200 focus:outline-none focus:border-gray-400"
                    >
                      {TIMEFRAMES.map(tf => <option key={tf} value={tf}>{tf}</option>)}
                    </select>
                  </div>
                  <div>
                    <label className="block text-xs text-white mb-1">Candles</label>
                    <input
                      type="number" value={candles} min={10} max={500}
                      onChange={e => setCandles(Math.max(10, Math.min(500, Number(e.target.value))))}
                      className="w-full bg-gray-800 border border-gray-600 rounded px-2 py-1.5 text-xs text-gray-200 focus:outline-none focus:border-gray-400"
                    />
                  </div>
                </div>
                <button
                  type="button" onClick={() => void runPreview()} disabled={running || !broker || !pair}
                  className="flex items-center gap-1.5 px-4 py-1.5 rounded bg-emerald-700 hover:bg-emerald-600 disabled:opacity-40 text-white text-xs font-medium transition-colors"
                >
                  <Play className="w-3.5 h-3.5" />
                  {running ? 'Running…' : 'Run'}
                </button>
                {runError && <p className="text-xs text-red-400 break-all">{runError}</p>}
                {previewUrl && !runError && (
                  <div className="mt-2 rounded overflow-hidden border border-gray-700">
                    <img
                      key={previewUrl}
                      src={previewUrl}
                      alt="Chartshot preview"
                      className="w-full h-auto"
                      onLoad={() => {
                        if (previewFilename) {
                          void fetch(`/chartshots/${encodeURIComponent(previewFilename)}`, { method: 'DELETE' })
                        }
                      }}
                    />
                  </div>
                )}
              </div>
            )}
          </div>

          {/* ── Config editor ────────────────────────────────────────────── */}
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold text-gray-200">
              Config: <span className="text-blue-400">{selected}</span>
            </h3>
            {selected !== 'default' && (
              <button
                type="button" onClick={deleteSelected}
                className="flex items-center gap-1 text-xs text-red-400 hover:text-red-300 transition-colors"
              >
                <Trash2 className="w-3.5 h-3.5" /> Delete
              </button>
            )}
          </div>

          {/* output_mode */}
          <div>
            <label className="block text-xs text-white mb-1.5">Output mode</label>
            <div className="flex gap-3">
              {(['temp','keep'] as OutputMode[]).map(m => (
                <label key={m} className="flex items-center gap-1.5 cursor-pointer">
                  <input
                    type="radio" name="output_mode" value={m}
                    checked={current.output_mode === m} onChange={() => updateSelected('output_mode', m)}
                    className="accent-blue-500"
                  />
                  <span className="text-xs text-gray-300">{m}</span>
                </label>
              ))}
            </div>
            <p className="mt-1.5 text-xs text-white">
              {current.output_mode === 'temp' && 'File is deleted after the LLM has processed the image.'}
              {current.output_mode === 'keep' && 'File is kept on disk after the LLM call.'}
            </p>
          </div>

          {/* style */}
          <div>
            <label className="block text-xs text-white mb-1.5">Chart style</label>
            <div className="flex gap-3">
              {(['dark','light'] as ChartStyle[]).map(s => (
                <label key={s} className="flex items-center gap-1.5 cursor-pointer">
                  <input
                    type="radio" name="style" value={s}
                    checked={current.style === s} onChange={() => updateSelected('style', s)}
                    className="accent-blue-500"
                  />
                  <span className="text-xs text-gray-300 capitalize">{s}</span>
                </label>
              ))}
            </div>
          </div>

          {/* ── Description ─────────────────────────────────────────────── */}
          <div>
            <label className="block text-xs text-white mb-1.5">
              Description
              <span className="ml-1.5 text-gray-600 font-normal normal-case">
                — appended to the LLM prompt when this chart is used in a snapshot
              </span>
            </label>
            <textarea
              value={current.description}
              onChange={e => updateSelected('description', e.target.value)}
              placeholder="e.g. This chart shows EURUSD M15 with EMA 20 and key swing levels. Focus on the reaction at the highlighted support zone."
              rows={4}
              className="w-full bg-gray-800 border border-gray-600 rounded px-3 py-2 text-xs text-gray-200 placeholder-gray-600 focus:outline-none focus:border-gray-400 resize-y"
            />
          </div>

          {/* ── Indicators ───────────────────────────────────────────────── */}
          <IndicatorsPanel
            indicators={current.indicators}
            onAdd={addIndicator}
            onRemove={removeIndicator}
            onUpdate={updateIndicator}
          />

          {/* ── Swing Levels ─────────────────────────────────────────────── */}
          <SwingLevelsPanel
            cfg={current.swing_levels}
            onChange={updateSwing}
          />

          {/* JSON preview */}
          <div>
            <label className="block text-xs text-white mb-1.5">Preview (system.json5 entry)</label>
            <pre className="rounded border border-gray-700 bg-gray-900 px-3 py-2 text-[11px] font-mono text-white overflow-x-auto whitespace-pre">
              {JSON.stringify({ [selected]: current }, null, 2)}
            </pre>
          </div>

        </div>
      </div>
    </div>

      {aiAssistantOpen && (
        <AiAssistantModal
          title="AI Assistant — Chartshot Config"
          contextFile="chartshot_config_assistant.md"
          contextData={JSON.stringify(root, null, 2)}
          contextDataLabel={selected}
          onClose={() => setAiAssistantOpen(false)}
        />
      )}
    </>
  )
}

// ─── IndicatorsPanel ──────────────────────────────────────────────────────────

function IndicatorsPanel({
  indicators,
  onAdd,
  onRemove,
  onUpdate,
}: {
  indicators: IndicatorConfig[]
  onAdd:    (name: IndicatorName) => void
  onRemove: (id: string) => void
  onUpdate: (id: string, patch: Partial<IndicatorConfig>) => void
}) {
  const [expanded, setExpanded] = useState(true)

  return (
    <div>
      <div
        className="flex items-center justify-between cursor-pointer mb-2"
        onClick={() => setExpanded(v => !v)}
      >
        <span className="font-semibold text-gray-300 text-xs uppercase tracking-wide">Indicators</span>
        <span className="text-gray-500">{expanded ? '▾' : '▸'}</span>
      </div>
      {expanded && (
        <div className="space-y-2">
          {/* Add buttons */}
          <div className="flex flex-wrap gap-1">
            {INDICATOR_DEFS.map(def => (
              <button
                key={def.name} type="button" onClick={() => onAdd(def.name)}
                className="flex items-center gap-0.5 px-2 py-0.5 rounded border border-gray-700 bg-gray-800 text-gray-300 hover:text-white text-xs"
              >
                <Plus className="w-2.5 h-2.5" />{def.label}
              </button>
            ))}
          </div>
          {/* Instance list */}
          {indicators.length === 0 && <p className="text-white text-xs">No indicators configured.</p>}
          {indicators.map(ind => (
            <div key={ind.id} className="flex items-center gap-1.5 bg-gray-900 rounded px-2 py-1.5 border border-gray-800 flex-wrap">
              {/* Color */}
              <input
                type="color" value={ind.color}
                onChange={e => onUpdate(ind.id, { color: e.target.value })}
                className="w-5 h-5 cursor-pointer rounded border-0 bg-transparent flex-shrink-0"
              />
              {/* Name */}
              <span className="text-gray-300 font-medium w-12 shrink-0 text-xs">{ind.name}</span>
              {/* Period */}
              <input
                type="number" min={ind.name === 'VWAP' ? 0 : 1} max={500} value={ind.period}
                onChange={e => onUpdate(ind.id, { period: Number(e.target.value) })}
                className="w-14 bg-gray-800 border border-gray-700 rounded px-1 text-gray-200 text-xs"
                title={ind.name === 'VWAP' ? 'Period (0 = daily reset)' : 'Period'}
              />
              {/* Timeframe */}
              <select
                value={ind.timeframe}
                onChange={e => onUpdate(ind.id, { timeframe: e.target.value })}
                className="bg-gray-800 border border-gray-700 rounded px-1 text-gray-200 text-xs"
              >
                {TIMEFRAMES.map(tf => <option key={tf} value={tf}>{tf}</option>)}
              </select>
              {/* Line style */}
              <select
                value={ind.line_style}
                onChange={e => onUpdate(ind.id, { line_style: Number(e.target.value) })}
                className="bg-gray-800 border border-gray-700 rounded px-1 text-gray-200 text-xs"
              >
                {LINE_STYLE_OPTS.map(opt => <option key={opt.value} value={opt.value}>{opt.label}</option>)}
              </select>
              {/* Line width */}
              <input
                type="number" min={1} max={4} value={ind.line_width}
                onChange={e => onUpdate(ind.id, { line_width: Number(e.target.value) })}
                className="w-8 bg-gray-800 border border-gray-700 rounded px-1 text-gray-200 text-xs"
                title="Line width"
              />
              {/* Smooth period (SLOPE_E / SLOPE_S only) */}
              {(['SLOPE_E','SLOPE_S'] as string[]).includes(ind.name) && (
                <input
                  type="number" min={1} max={20} value={ind.smooth_period ?? 1}
                  onChange={e => onUpdate(ind.id, { smooth_period: Number(e.target.value) })}
                  className="w-14 bg-gray-800 border border-amber-700 rounded px-1 text-amber-200 text-xs"
                  title="Smooth period"
                />
              )}
              {/* Delete */}
              <button
                type="button" onClick={() => onRemove(ind.id)}
                className="text-gray-500 hover:text-red-400 ml-auto flex-shrink-0"
              >
                <Trash2 className="w-3 h-3" />
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ─── SwingLevelsPanel ─────────────────────────────────────────────────────────

function SwingLevelsPanel({
  cfg,
  onChange,
}: {
  cfg:      SwingConfig
  onChange: (patch: Partial<SwingConfig>) => void
}) {
  const [expanded, setExpanded] = useState(true)

  return (
    <div>
      <div
        className="flex items-center justify-between cursor-pointer mb-2"
        onClick={() => setExpanded(v => !v)}
      >
        <label
          className="flex items-center gap-1.5 cursor-pointer"
          onClick={e => e.stopPropagation()}
        >
          <input
            type="checkbox" checked={cfg.enabled}
            onChange={e => onChange({ enabled: e.target.checked })}
            className="accent-emerald-500"
          />
          <span className="font-semibold text-gray-300 text-xs uppercase tracking-wide">Swing Levels</span>
        </label>
        <span className="text-gray-500">{expanded ? '▾' : '▸'}</span>
      </div>
      {expanded && cfg.enabled && (
        <div className="space-y-2 text-xs">
          {/* Row 1: TF, Count, ATR, Gap */}
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-gray-400">TF</span>
            <select
              value={cfg.timeframe} onChange={e => onChange({ timeframe: e.target.value })}
              className="bg-gray-800 border border-gray-700 rounded px-1 text-gray-200"
            >
              {TIMEFRAMES.map(tf => <option key={tf} value={tf}>{tf}</option>)}
            </select>
            <span className="text-gray-400">Count</span>
            <input
              type="number" min={1} max={20} value={cfg.count}
              onChange={e => onChange({ count: Number(e.target.value) })}
              className="w-10 bg-gray-800 border border-gray-700 rounded px-1 text-gray-200"
            />
            <span className="text-gray-400">ATR</span>
            <input
              type="number" min={1} max={200} value={cfg.atr_period}
              onChange={e => onChange({ atr_period: Math.max(1, Math.min(200, Number(e.target.value))) })}
              className="w-12 bg-gray-800 border border-gray-700 rounded px-1 text-gray-200"
              title="ATR period for cluster gap"
            />
            <span className="text-gray-400">Gap</span>
            <input
              type="number" min={0} max={5} step={0.1} value={cfg.min_gap_atr}
              onChange={e => onChange({ min_gap_atr: Math.max(0, Math.min(5, Number(e.target.value))) })}
              className="w-12 bg-gray-800 border border-gray-700 rounded px-1 text-gray-200"
              title="Min gap as ATR multiple"
            />
          </div>
          {/* Row 2: Next/Prominent, HL/OC */}
          <div className="flex items-center gap-2 flex-wrap">
            <div className="flex rounded border border-gray-700 overflow-hidden">
              {(['nearest','prominent'] as const).map(s => (
                <button
                  key={s} type="button" onClick={() => onChange({ sort_by: s })}
                  className={`px-2 py-0.5 ${cfg.sort_by === s ? 'bg-emerald-600 text-white' : 'bg-gray-800 text-gray-400 hover:text-white'}`}
                >
                  {s === 'nearest' ? 'Next' : 'Prominent'}
                </button>
              ))}
            </div>
            <div className="flex rounded border border-gray-700 overflow-hidden">
              {(['HL','OC'] as const).map(src => (
                <button
                  key={src} type="button" onClick={() => onChange({ price_source: src })}
                  className={`px-2 py-0.5 ${cfg.price_source === src ? 'bg-emerald-600 text-white' : 'bg-gray-800 text-gray-400 hover:text-white'}`}
                >
                  {src}
                </button>
              ))}
            </div>
          </div>
          {/* Row 3: Width, Style */}
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-gray-400">Width</span>
            <input
              type="number" min={1} max={5} value={cfg.line_width}
              onChange={e => onChange({ line_width: Math.max(1, Math.min(5, Number(e.target.value))) })}
              className="w-10 bg-gray-800 border border-gray-700 rounded px-1 text-gray-200"
            />
            <span className="text-gray-400">Style</span>
            <select
              value={cfg.line_style} onChange={e => onChange({ line_style: Number(e.target.value) })}
              className="bg-gray-800 border border-gray-700 rounded px-1 text-gray-200"
            >
              {LINE_STYLE_OPTS.map(opt => <option key={opt.value} value={opt.value}>{opt.label}</option>)}
            </select>
          </div>
        </div>
      )}
    </div>
  )
}
