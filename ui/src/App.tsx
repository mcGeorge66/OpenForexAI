/**
 * App — root component.
 *
 * Manages:
 * - Active top-level section (Action / Monitor / Config / Test)
 * - Active sub-menu item per section
 * - Single shared useMonitoringStream (all monitor views share the same buffer)
 * - Layout: Header → TopMenu → (SubMenu | MainArea)
 */

import { useState } from 'react'
import { Header } from '@/components/layout/Header'
import { TopMenu, type TopSection } from '@/components/layout/TopMenu'
import { SubMenu } from '@/components/layout/SubMenu'
import { useMonitoringStream } from '@/hooks/useMonitoringStream'
import { api } from '@/api/client'

// Views
import { InitialPage } from '@/components/views/action/InitialPage'
import { AgentChat } from '@/components/views/action/AgentChat'
import { EventStream } from '@/components/views/monitor/EventStream'
import { ConfigViewer } from '@/components/views/config/ConfigViewer'
import { ModuleConfigViewer } from '@/components/views/config/ModuleConfigViewer'
import { EventRoutingEditor } from '@/components/views/config/EventRoutingEditor'
import { BridgeToolsEditor } from '@/components/views/config/BridgeToolsEditor'
import { AgentConfigWizard } from '@/components/views/config/AgentConfigWizard'
import { PackageManager } from '@/components/views/config/PackageManager'
import { InformationView } from '@/components/views/config/InformationView'
import { ToolExecutor } from '@/components/views/test/ToolExecutor'
import { LlmChecker } from '@/components/views/test/LlmChecker'

const MONITOR_FILTERS: Record<string, string[] | undefined> = {
  all:  undefined,
  llm:  ['llm_request', 'llm_response', 'llm_error'],
  tool: ['tool_call_started', 'tool_call_completed', 'tool_call_failed'],
  bus:  [
    'event_bus_message', 'agent_signal_generated', 'agent_decision_made',
    'routing_reloaded', 'routing_reload_failed', 'agent_queue_full',
  ],
  broker: [
    'broker_connected', 'broker_disconnected', 'broker_reconnecting', 'broker_error',
    'broker_http_request', 'broker_http_response',
    'account_status_updated', 'account_poll_error',
    'm5_candle_fetched', 'm5_candle_queued',
  ],
  data: [
    'm5_candle_fetched', 'm5_candle_queued', 'candle_gap_detected',
    'candle_repair_started', 'candle_repair_completed', 'candle_repair_failed',
    'timeframe_calculated', 'data_container_access',
    'sync_check_started', 'sync_check_completed', 'sync_discrepancy_found',
  ],
}

const CONFIG_VIEWS: Record<string, { pathLabel: string; title: string; load: () => Promise<string>; save: (content: Record<string, unknown> | string) => Promise<unknown> }> = {
  system: {
    pathLabel: 'D:\\GitHub\\GHG\\OpenForexAI\\config\\system.json5',
    title: 'System Configuration',
    load: api.getSystemConfigText,
    save: api.saveSystemConfig,
  },
  agent_tools: {
    pathLabel: 'D:\\GitHub\\GHG\\OpenForexAI\\config\\RunTime\\agent_tools.json5',
    title: 'Agent Tools Configuration',
    load: () => api.getConfigFileText('agent_tools'),
    save: (content: Record<string, unknown> | string) => api.saveConfigFile('agent_tools', content),
  },
  event_routing: {
    pathLabel: 'D:\\GitHub\\GHG\\OpenForexAI\\config\\RunTime\\event_routing.json5',
    title: 'Event Routing Rules',
    load: () => api.getConfigFileText('event_routing'),
    save: (content: Record<string, unknown> | string) => api.saveConfigFile('event_routing', content),
  },
}

const DEFAULT_SUB: Record<TopSection, string> = {
  action:  'initial',
  monitor: 'all',
  config:  'information',
  test:    'llm_checker',
}

export default function App() {
  const [section, setSection] = useState<TopSection>('action')
  const [subItems, setSubItems] = useState<Record<TopSection, string>>(DEFAULT_SUB)

  const activeSub = subItems[section]

  const handleSection = (s: TopSection) => {
    setSection(s)
  }

  const handleSub = (id: string) => {
    setSubItems(prev => ({ ...prev, [section]: id }))
  }

  const { events, connected, lastUpdate, clear } = useMonitoringStream()

  function renderMain() {
    switch (section) {
      case 'action':
        if (activeSub === 'initial') return <InitialPage />
        if (activeSub === 'chat') return <AgentChat />
        return null

      case 'monitor': {
        const filter = MONITOR_FILTERS[activeSub]
        return (
          <EventStream
            events={events}
            connected={connected}
            filter={filter}
            onClear={clear}
          />
        )
      }

      case 'config': {
        if (activeSub === 'information') return <InformationView key="information" />
        if (activeSub === 'package_manager') return <PackageManager key="package-manager" />
        if (activeSub === 'agent_wizard') return <AgentConfigWizard key="agent-wizard" />
        if (activeSub === 'llm') return <ModuleConfigViewer moduleType="llm" key="llm" />
        if (activeSub === 'broker') return <ModuleConfigViewer moduleType="broker" key="broker" />
        if (activeSub === 'event_routing') return <EventRoutingEditor key="event-routing" />
        if (activeSub === 'bridge_tools') return <BridgeToolsEditor key="bridge-tools" />
        const cfg = CONFIG_VIEWS[activeSub]
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
        if (activeSub === 'llm_checker') return <LlmChecker />
        if (activeSub === 'tool_exec') return <ToolExecutor />
        return null

      default:
        return null
    }
  }

  return (
    <div className="flex flex-col h-screen overflow-hidden">
      <Header lastUpdate={lastUpdate} connected={connected} />
      <TopMenu active={section} onSelect={handleSection} />

      <div className="flex flex-1 overflow-hidden">
        <SubMenu
          section={section}
          active={activeSub}
          onSelect={handleSub}
        />
        <main className="flex-1 overflow-hidden">
          {renderMain()}
        </main>
      </div>
    </div>
  )
}




