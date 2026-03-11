/**
 * SubMenu — vertical left-panel menu for the active top-level section.
 */

import type { TopSection } from './TopMenu'

export type SubItem = {
  id: string
  label: string
}

const SUB_ITEMS: Record<TopSection, SubItem[]> = {
  action: [
    { id: 'chat',         label: 'Agent Chat' },
  ],
  monitor: [
    { id: 'all',          label: 'All Events'   },
    { id: 'llm',          label: 'LLM Events'   },
    { id: 'tool',         label: 'Tool Events'  },
    { id: 'bus',          label: 'Bus Events'    },
    { id: 'broker',       label: 'Broker Events' },
    { id: 'data',         label: 'Data Events'   },
  ],
  config: [
    { id: 'information',  label: 'Information'   },
    { id: 'agent_wizard', label: 'Agent Wizard'  },
    { id: 'system',       label: 'System Config'  },
    { id: 'agent_tools',  label: 'Agent Tools'    },
    { id: 'bridge_tools', label: 'Bridge Tools'   },
    { id: 'event_routing',label: 'Event Routing'  },
    { id: 'llm',          label: 'LLM Modules'    },
    { id: 'broker',       label: 'Broker Modules' },
  ],
  test: [
    { id: 'llm_checker', label: 'LLM Checker'   },
    { id: 'tool_exec',    label: 'Tool Executor'  },
  ],
}

interface SubMenuProps {
  section: TopSection
  active: string
  onSelect: (id: string) => void
}

export function SubMenu({ section, active, onSelect }: SubMenuProps) {
  const items = SUB_ITEMS[section] ?? []

  return (
    <aside className="w-44 flex-shrink-0 bg-gray-900 border-r border-gray-700 overflow-y-auto">
      <ul className="py-2">
        {items.map(item => (
          <li key={item.id}>
            <button
              onClick={() => onSelect(item.id)}
              className={[
                'w-full text-left px-4 py-2 text-sm transition-colors',
                active === item.id
                  ? 'bg-emerald-900/40 text-emerald-300 border-l-2 border-emerald-400'
                  : 'text-gray-400 hover:text-gray-200 hover:bg-gray-800 border-l-2 border-transparent',
              ].join(' ')}
            >
              {item.label}
            </button>
          </li>
        ))}
      </ul>
    </aside>
  )
}

export { SUB_ITEMS }


