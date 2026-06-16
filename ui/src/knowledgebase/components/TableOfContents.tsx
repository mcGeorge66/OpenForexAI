interface Props {
  content: string
}

interface Heading {
  level: number
  text: string
  slug: string
}

export function headingSlug(text: string): string {
  return text.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '')
}

function parseHeadings(md: string): Heading[] {
  const lines = md.split('\n')
  const headings: Heading[] = []
  const seen = new Map<string, number>()
  for (const line of lines) {
    const m = line.match(/^(#{1,3})\s+(.+)/)
    if (m) {
      const text = m[2].trim()
      const base = headingSlug(text)
      const count = seen.get(base) ?? 0
      seen.set(base, count + 1)
      const slug = count === 0 ? base : `${base}-${count}`
      headings.push({ level: m[1].length, text, slug })
    }
  }
  return headings
}

export function TableOfContents({ content }: Props) {
  const headings = parseHeadings(content)

  if (headings.length === 0) {
    return (
      <div className="p-3">
        <p className="text-xs text-gray-600">Keine Überschriften</p>
      </div>
    )
  }

  return (
    <div className="p-3">
      <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">Inhalt</p>
      <nav className="space-y-0.5">
        {headings.map((h, i) => (
          <button
            key={i}
            className="block w-full text-left text-xs text-gray-400 hover:text-gray-200 transition-colors py-0.5 truncate"
            style={{ paddingLeft: `${(h.level - 1) * 10}px` }}
            onClick={() => {
              const el = document.getElementById(`heading-${h.slug}`)
              el?.scrollIntoView({ behavior: 'smooth', block: 'start' })
            }}
            title={h.text}
          >
            {h.text}
          </button>
        ))}
      </nav>
    </div>
  )
}
