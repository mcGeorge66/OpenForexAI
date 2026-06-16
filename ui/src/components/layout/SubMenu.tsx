/**
 * SubMenu — vertical left-panel menu for the active top-level section.
 */

import type { TopSection } from './TopMenu'

export type SubItem = {
  id: string
  label: string
  divider?: boolean
  heading?: boolean
}

const SUB_ITEMS: Record<TopSection, SubItem[]> = {
  action: [
    { id: 'initial',        label: 'Initial'         },
    { id: 'chat',           label: 'Agent Chat'      },
    { id: 'orderbook',      label: 'Orderbook'       },
    { id: 'chart_analysis', label: 'Chart Analysis'  },
    { id: '__div_kb',       label: '', divider: true  },
    { id: 'knowledgebase',  label: 'Knowledgebase'   },
  ],
  monitor: [
    { id: 'all',          label: 'All Events'   },
    { id: 'llm',          label: 'LLM Events'   },
    { id: 'tool',         label: 'Tool Events'  },
    { id: 'bus',          label: 'Bus Events'    },
    { id: 'broker',       label: 'Broker Events' },
    { id: 'data',         label: 'Data Events'   },
    { id: 'core',         label: 'Core Events'   },
    { id: 'agent',        label: 'Agent Events'  },
    { id: 'entity',       label: 'Entity Events' },
  ],
  config: [
    { id: 'information',     label: 'Information'      },
    { id: '__div0',          label: '', divider: true   },
    { id: 'agent_wizard',    label: 'Agent Config'     },
    { id: 'ec_wizard',       label: 'Entity Config'    },
    { id: 'snapshot_config', label: 'Snapshot Config'  },
    { id: 'decision_prompt', label: 'Decision Prompt'  },
    { id: 'bridge_tools',    label: 'Bridge Tools'     },
    { id: 'event_routing',   label: 'Event Routing'    },
    { id: '__div1',          label: '', divider: true   },
    { id: 'ai_assistant',    label: 'AI-Assistant'     },
    { id: 'system',          label: 'System Config'    },
    { id: 'helper_config',   label: 'Helper Config'    },
    { id: '__div2',          label: '', divider: true   },
    { id: 'package_manager', label: 'Package Manager'  },
    { id: 'broker',          label: 'Broker Modules'   },
    { id: 'llm',             label: 'LLM Modules'      },
    { id: '__div3',          label: '', divider: true   },
    { id: '__h_test',        label: 'Test', heading: true },
    { id: 'llm_checker',     label: 'LLM Checker'      },
    { id: 'tool_exec',       label: 'Tool Executor'    },
  ],
  test: [],
}

interface SubMenuProps {
  section: TopSection
  active: string
  onSelect: (id: string) => void
  itemsOverride?: SubItem[]
  emptyLabel?: string
}

export function SubMenu({ section, active, onSelect, itemsOverride, emptyLabel }: SubMenuProps) {
  const items = itemsOverride ?? SUB_ITEMS[section] ?? []

  if (items.length === 0) {
    return (
      <aside className="w-44 flex-shrink-0 bg-gray-900 border-r border-gray-700 overflow-y-auto">
        <div className="px-4 py-3 text-xs text-gray-500">
          {emptyLabel ?? 'No items'}
        </div>
      </aside>
    )
  }

  return (
    <aside className="w-44 flex-shrink-0 bg-gray-900 border-r border-gray-700 overflow-y-auto">
      <ul className="py-2">
        {items.map(item => (
          <li key={item.id}>
            {item.divider ? (
              <div className="mx-3 my-2 border-t border-gray-800" />
            ) : item.heading ? (
              <div className="px-4 pt-1 pb-1 text-xs font-semibold text-gray-300 uppercase tracking-wide select-none">
                {item.label}
              </div>
            ) : (
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
            )}
          </li>
        ))}
      </ul>
    </aside>
  )
}

export { SUB_ITEMS }


