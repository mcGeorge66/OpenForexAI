/**
 * TopMenu — horizontal tab bar: Action | Test | Config | Monitor | Handbook / Handbuch (popup)
 */

import { BookOpen } from 'lucide-react'

export type TopSection = 'action' | 'monitor' | 'config' | 'test'

interface TopMenuProps {
  active: TopSection
  onSelect: (section: TopSection) => void
  onHandbook: (lang: 'en' | 'de') => void
}

const ITEMS: Array<{ id: TopSection; label: string }> = [
  { id: 'action',  label: 'Action'  },
  { id: 'config',  label: 'Config'  },
  { id: 'monitor', label: 'Monitor' },
]

export function TopMenu({ active, onSelect, onHandbook }: TopMenuProps) {
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
      <div className="flex-1" />
      <div className="flex items-center border-l border-gray-700 ml-2 pl-2">
        <button
          onClick={() => onHandbook('en')}
          className="flex items-center gap-1.5 px-3 py-2 text-sm text-gray-400 hover:text-gray-200 transition-colors"
          title="Open Handbook (English)"
        >
          <BookOpen className="w-4 h-4" />
          Handbook
        </button>
        <button
          onClick={() => onHandbook('de')}
          className="px-3 py-2 text-sm text-gray-400 hover:text-gray-200 transition-colors"
          title="Handbuch öffnen (Deutsch)"
        >
          Handbuch
        </button>
      </div>
    </nav>
  )
}
