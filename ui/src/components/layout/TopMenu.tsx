/**
 * TopMenu — horizontal tab bar: Action | Monitor | Config | Test
 */

export type TopSection = 'action' | 'monitor' | 'config' | 'test'

interface TopMenuProps {
  active: TopSection
  onSelect: (section: TopSection) => void
}

const ITEMS: Array<{ id: TopSection; label: string }> = [
  { id: 'action',  label: 'Action'  },
  { id: 'monitor', label: 'Monitor' },
  { id: 'config',  label: 'Config'  },
  { id: 'test',    label: 'Test'    },
]

export function TopMenu({ active, onSelect }: TopMenuProps) {
  return (
    <nav className="flex items-center gap-0 px-2 bg-gray-850 border-b border-gray-700 flex-shrink-0"
         style={{ backgroundColor: '#111827' }}>
      {ITEMS.map(item => (
        <button
          key={item.id}
          onClick={() => onSelect(item.id)}
          className={[
            'px-5 py-2.5 text-sm font-medium transition-colors border-b-2 -mb-px',
            active === item.id
              ? 'border-emerald-400 text-emerald-400'
              : 'border-transparent text-gray-400 hover:text-gray-200 hover:border-gray-500',
          ].join(' ')}
        >
          {item.label}
        </button>
      ))}
    </nav>
  )
}
