/**
 * App — root component.
 *
 * Manages:
 * - Active top-level section (Action / Monitor / Config / Test)
 * - Active sub-menu item per section
 * - Single shared useMonitoringStream (all monitor views share the same buffer)
 * - Layout: Header → TopMenu → (SubMenu | MainArea)
 *
 * When the URL contains ?handbook=1, the app renders only HandbookView (popup mode).
 */

import { useEffect, useMemo, useState } from 'react'
import { Header } from '@/components/layout/Header'
import { TopMenu, type TopSection } from '@/components/layout/TopMenu'
import { SubMenu } from '@/components/layout/SubMenu'
import { useMonitoringStream } from '@/hooks/useMonitoringStream'
import { api } from '@/api/client'
import { useProjectRoot, joinPath } from '@/api/useProjectRoot'

// Views
import { InitialPage } from '@/components/views/action/InitialPage'
import { AgentChat } from '@/components/views/action/AgentChat'
import { Orderbook } from '@/components/views/action/Orderbook'
import { ChartAnalysis } from '@/components/views/action/ChartAnalysis'
import { EventStream, type SavedMonitorFilter } from '@/components/views/monitor/EventStream'
import { ConfigViewer } from '@/components/views/config/ConfigViewer'
import { ModuleConfigViewer } from '@/components/views/config/ModuleConfigViewer'
import { EventRoutingEditor } from '@/components/views/config/EventRoutingEditor'
import { BridgeToolsEditor } from '@/components/views/config/BridgeToolsEditor'
import { AgentConfigWizard } from '@/components/views/config/AgentConfigWizard'
import { EventComposerConfigWizard } from '@/components/views/config/EventComposerConfigWizard'
import { HelperConfigViewer } from '@/components/views/config/HelperConfigViewer'
import { DecisionPromptConfigEditor, SnapshotConfigEditor } from '@/components/views/config/ProfileConfigEditors'
import { PackageManager } from '@/components/views/config/PackageManager'
import { LlmContextEditor } from '@/components/views/config/LlmContextEditor'
import { InformationView } from '@/components/views/config/InformationView'
import { ToolExecutor } from '@/components/views/test/ToolExecutor'
import { LlmChecker } from '@/components/views/test/LlmChecker'
import { HandbookView } from '@/components/views/handbook/HandbookView'

// The app subscribes to one shared, unfiltered monitoring stream. Per-module
// filtering and arrow-direction computation live in eventFlow.ts.

type ConfigViewEntry = {
  pathLabel: string
  title: string
  load: () => Promise<string>
  save: (content: Record<string, unknown> | string) => Promise<unknown>
}

function buildConfigViews(root: string): Record<string, ConfigViewEntry> {
  const systemPath = root ? joinPath(root, 'config', 'system.json5') : 'config/system.json5'
  const routingPath = root ? joinPath(root, 'config', 'RunTime', 'event_routing.json5') : 'config/RunTime/event_routing.json5'
  return {
    system: {
      pathLabel: systemPath,
      title: 'System Configuration',
      load: api.getSystemConfigText,
      save: api.saveSystemConfig,
    },
    event_routing: {
      pathLabel: routingPath,
      title: 'Event Routing Rules',
      load: () => api.getConfigFileText('event_routing'),
      save: (content: Record<string, unknown> | string) => api.saveConfigFile('event_routing', content),
    },
  }
}

const HANDBOOK_FILE: Record<string, string> = {
  // action
  'action:initial':         'ui.action.initial',
  'action:chat':            'ui.action.chat',
  'action:orderbook':       'ui.action.orderbook',
  'action:chart_analysis':  'ui.action.chart_analysis',
  // monitor
  'monitor:all':       'ui.monitor',
  'monitor:llm':       'ui.monitor',
  'monitor:tool':      'ui.monitor',
  'monitor:bus':       'ui.monitor',
  'monitor:broker':    'ui.monitor',
  'monitor:data':      'ui.monitor',
  'monitor:core':      'ui.monitor',
  'monitor:agent':     'ui.monitor',
  // config
  'config:information':    'ui.config.information',
  'config:agent_wizard':   'ui.config.agent_config',
  'config:snapshot_config':'ui.config.snapshot_config',
  'config:decision_prompt':'ui.config.decision_prompt',
  'config:bridge_tools':   'ui.config.bridge_tools',
  'config:event_routing':  'ui.config.event_routing',
  'config:system':         'ui.config.system_config',
  'config:helper_config':  'ui.config.helper_config',
  'config:package_manager':'ui.config.package_manager',
  'config:broker':         'ui.config.broker_modules',
  'config:llm':            'ui.config.llm_modules',
  'config:entity_config':  'ui.config.entity_config',
  'config:llm_checker': 'ui.test.llm_checker',
  'config:tool_exec':   'ui.test.tool_executor',
}

function resolveHandbookFile(section: TopSection, sub: string, lang: 'en' | 'de'): string {
  const base = HANDBOOK_FILE[`${section}:${sub}`] ?? `ui.${section}`
  return `${base}.${lang}.md`
}

const DEFAULT_SUB: Record<TopSection, string> = {
  action:  'initial',
  monitor: '__none__',
  config:  'information',
  test:    'llm_checker',  // kept for type completeness, tab is hidden
}

function normaliseSavedMonitorFilters(value: unknown): SavedMonitorFilter[] {
  if (!Array.isArray(value)) return []
  return value
    .filter((item): item is Record<string, unknown> => !!item && typeof item === 'object')
    .map(item => ({
      id: typeof item.id === 'string' ? item.id : `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`,
      name: typeof item.name === 'string' ? item.name : 'Unnamed filter',
      definition: (() => {
        const rawDefinition = item.definition && typeof item.definition === 'object'
          ? item.definition as Record<string, unknown>
          : null
        const rawRules = Array.isArray(rawDefinition?.rules) ? rawDefinition.rules : []
        const legacyMode = rawDefinition?.mode === 'OR' ? 'OR' : 'AND'
        const legacyNegated = rawDefinition?.negated === true
        return {
          rules: rawRules
            .filter((rule): rule is Record<string, unknown> => !!rule && typeof rule === 'object')
            .map((rule, index) => ({
              ...(rule as SavedMonitorFilter['definition']['rules'][number]),
              join: (typeof rule.join === 'string'
                ? rule.join
                : index === 0
                  ? 'START'
                  : legacyMode === 'OR'
                    ? (legacyNegated ? 'OR_NOT' : 'OR')
                    : (legacyNegated ? 'AND_NOT' : 'AND')) as SavedMonitorFilter['definition']['rules'][number]['join'],
            })),
        }
      })(),
      options: {
        includeResponses: !(item.options && typeof item.options === 'object')
          || (item.options as Record<string, unknown>).includeResponses !== false,
        showOrphans: !(item.options && typeof item.options === 'object')
          || (item.options as Record<string, unknown>).showOrphans !== false,
      },
    }))
}

function extractSavedMonitorFiltersFromSystemConfig(config: Record<string, unknown> | null | undefined): SavedMonitorFilter[] {
  const system = config?.system
  if (!system || typeof system !== 'object') return []
  const ui = (system as Record<string, unknown>).ui
  if (!ui || typeof ui !== 'object') return []
  const monitor = (ui as Record<string, unknown>).monitor
  if (!monitor || typeof monitor !== 'object') return []
  return normaliseSavedMonitorFilters((monitor as Record<string, unknown>).saved_filters)
}

function withSavedMonitorFilters(
  config: Record<string, unknown>,
  filters: SavedMonitorFilter[],
): Record<string, unknown> {
  const next = structuredClone(config)
  const system = (next.system && typeof next.system === 'object') ? next.system as Record<string, unknown> : {}
  next.system = system
  const ui = (system.ui && typeof system.ui === 'object') ? system.ui as Record<string, unknown> : {}
  system.ui = ui
  const monitor = (ui.monitor && typeof ui.monitor === 'object') ? ui.monitor as Record<string, unknown> : {}
  ui.monitor = monitor
  monitor.saved_filters = filters
  return next
}

// Standalone handbook popup — renders when ?handbook=1 is in the URL
function HandbookPopup() {
  return (
    <div className="flex flex-col h-screen overflow-hidden bg-gray-950">
      <div className="flex items-center px-4 py-2 bg-gray-900 border-b border-gray-700 flex-shrink-0">
        <span className="text-sm font-semibold text-emerald-400">Handbook</span>
      </div>
      <div className="flex-1 overflow-hidden">
        <HandbookView />
      </div>
    </div>
  )
}

export default function App() {
  // Popup mode: render only the handbook when ?handbook=1
  if (new URLSearchParams(window.location.search).get('handbook') === '1') {
    return <HandbookPopup />
  }

  const [section, setSection] = useState<TopSection>('action')
  const [subItems, setSubItems] = useState<Record<TopSection, string>>(DEFAULT_SUB)
  const [savedMonitorFilters, setSavedMonitorFilters] = useState<SavedMonitorFilter[]>([])

  const activeSub = subItems[section]
  const monitorSubItems = savedMonitorFilters.map(filter => ({ id: filter.id, label: filter.name }))

  const projectRoot = useProjectRoot()
  const configViews = useMemo(() => buildConfigViews(projectRoot), [projectRoot])

  useEffect(() => {
    let cancelled = false
    void api.getSystemConfig()
      .then(cfg => {
        if (!cancelled) setSavedMonitorFilters(extractSavedMonitorFiltersFromSystemConfig(cfg))
      })
      .catch(() => {
        if (!cancelled) setSavedMonitorFilters([])
      })
    return () => { cancelled = true }
  }, [])

  const handleSection = (s: TopSection) => {
    setSection(s)
  }

  const handleSavedMonitorFiltersChange = async (next: SavedMonitorFilter[]) => {
    setSavedMonitorFilters(next)
    if (section === 'monitor' && activeSub !== '__none__' && !next.some(item => item.id === activeSub)) {
      setSubItems(prev => ({ ...prev, monitor: '__none__' }))
    }
    const latest = await api.getSystemConfig()
    await api.saveSystemConfig(withSavedMonitorFilters(latest, next))
  }

  const handleSub = (id: string) => {
    if (id === 'knowledgebase') {
      window.open(
        `${window.location.origin}${window.location.pathname}?knowledgebase=1`,
        'knowledgebase',
        'width=1400,height=900,resizable=yes',
      )
      return
    }
    setSubItems(prev => ({ ...prev, [section]: id }))
  }

  const handleHandbook = (lang: 'en' | 'de') => {
    const file = resolveHandbookFile(section, activeSub, lang)
    window.open(
      `${window.location.origin}${window.location.pathname}?handbook=1&file=${encodeURIComponent(file)}`,
      'handbook',
      'width=1024,height=768,resizable=yes,scrollbars=yes',
    )
  }

  // Always subscribe without a server-side filter so "All Events" is truly
  // unfiltered and the other monitor tabs are only view-level filters.
  const { events, connected, lastUpdate, clear } = useMonitoringStream()

  function renderMain() {
    switch (section) {
      case 'action':
        if (activeSub === 'initial') return <InitialPage />
        if (activeSub === 'chat') return <AgentChat />
        if (activeSub === 'orderbook') return <Orderbook />
        if (activeSub === 'chart_analysis') return <ChartAnalysis />
        return null

      case 'monitor':
        return (
          <EventStream
            events={events}
            connected={connected}
            activeQuickFilterId={activeSub === '__none__' ? null : activeSub}
            savedQuickFilters={savedMonitorFilters}
            onSavedQuickFiltersChange={handleSavedMonitorFiltersChange}
            onQuickFilterActivated={(filterId) => {
              setSubItems(prev => ({ ...prev, monitor: filterId ?? '__none__' }))
            }}
            onClear={clear}
          />
        )

      case 'config': {
        if (activeSub === 'information') return <InformationView key="information" />
        if (activeSub === 'agent_wizard') return <AgentConfigWizard key="agent-wizard" />
        if (activeSub === 'ec_wizard') return <EventComposerConfigWizard key="ec-wizard" />
        if (activeSub === 'snapshot_config') return <SnapshotConfigEditor key="snapshot-config" />
        if (activeSub === 'decision_prompt') return <DecisionPromptConfigEditor key="decision-prompt" />
        if (activeSub === 'bridge_tools') return <BridgeToolsEditor key="bridge-tools" />
        if (activeSub === 'event_routing') return <EventRoutingEditor key="event-routing" />
        if (activeSub === 'helper_config') return <HelperConfigViewer key="helper-config" />
        if (activeSub === 'package_manager') return <PackageManager key="package-manager" />
        if (activeSub === 'broker') return <ModuleConfigViewer moduleType="broker" key="broker" />
        if (activeSub === 'llm') return <ModuleConfigViewer moduleType="llm" key="llm" />
        if (activeSub === 'ai_assistant') return <LlmContextEditor />
        if (activeSub === 'llm_checker') return <LlmChecker />
        if (activeSub === 'tool_exec') return <ToolExecutor />
        const cfg = configViews[activeSub]
        if (!cfg) return <p className="p-4 text-gray-500 text-sm">Select a config file</p>
        return (
          <ConfigViewer
            pathLabel={cfg.pathLabel}
            title={cfg.title}
            loadConfig={cfg.load}
            saveConfig={cfg.save}
            key={activeSub}
          />
        )
      }

      case 'test':
        return null

      default:
        return null
    }
  }

  return (
    <div className="flex flex-col h-screen overflow-hidden">
      <Header lastUpdate={lastUpdate} connected={connected} />
      <TopMenu active={section} onSelect={handleSection} onHandbook={handleHandbook} />

      <div className="flex flex-1 overflow-hidden">
        <SubMenu
          section={section}
          active={activeSub}
          onSelect={handleSub}
          itemsOverride={section === 'monitor' ? monitorSubItems : undefined}
          emptyLabel={section === 'monitor' ? 'No saved filters' : undefined}
        />
        <main className="flex-1 overflow-hidden">
          {renderMain()}
        </main>
      </div>
    </div>
  )
}
