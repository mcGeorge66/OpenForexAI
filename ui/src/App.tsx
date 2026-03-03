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

// Views
import { AgentChat } from '@/components/views/action/AgentChat'
import { EventStream } from '@/components/views/monitor/EventStream'
import { ConfigViewer } from '@/components/views/config/ConfigViewer'
import { ToolExecutor } from '@/components/views/test/ToolExecutor'

// ── Monitor filter definitions ────────────────────────────────────────────────

const MONITOR_FILTERS: Record<string, string[] | undefined> = {
  all:  undefined,
  llm:  ['llm_request', 'llm_response', 'llm_error'],
  tool: ['tool_call_started', 'tool_call_completed', 'tool_call_failed'],
  bus:  [
    'event_bus_message', 'agent_signal_generated', 'agent_decision_made',
    'routing_reloaded', 'routing_reload_failed', 'agent_queue_full',
  ],
  data: [
    'm5_candle_fetched', 'm5_candle_queued', 'candle_gap_detected',
    'candle_repair_started', 'candle_repair_completed', 'candle_repair_failed',
    'timeframe_calculated', 'data_container_access',
    'sync_check_started', 'sync_check_completed', 'sync_discrepancy_found',
  ],
}

// ── Config view URLs ──────────────────────────────────────────────────────────

const CONFIG_VIEWS: Record<string, { url: string; title: string }> = {
  system:        { url: '/config/view',                  title: 'System Configuration (secrets masked)' },
  agent_tools:   { url: '/config/files/agent_tools',     title: 'Agent Tools Configuration' },
  event_routing: { url: '/config/files/event_routing',   title: 'Event Routing Rules' },
}

// Default sub-items per section
const DEFAULT_SUB: Record<TopSection, string> = {
  action:  'chat',
  monitor: 'all',
  config:  'system',
  test:    'tool_exec',
}

export default function App() {
  const [section, setSection] = useState<TopSection>('monitor')
  const [subItems, setSubItems] = useState<Record<TopSection, string>>(DEFAULT_SUB)

  const activeSub = subItems[section]

  const handleSection = (s: TopSection) => {
    setSection(s)
  }

  const handleSub = (id: string) => {
    setSubItems(prev => ({ ...prev, [section]: id }))
  }

  // Single shared monitoring stream — always active
  const { events, connected, lastUpdate, clear } = useMonitoringStream()

  // ── Render main area content ───────────────────────────────────────────────

  function renderMain() {
    switch (section) {
      case 'action':
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
        const cfg = CONFIG_VIEWS[activeSub]
        if (!cfg) return <p className="p-4 text-gray-500 text-sm">Select a config file</p>
        return <ConfigViewer url={cfg.url} title={cfg.title} key={activeSub} />
      }

      case 'test':
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
