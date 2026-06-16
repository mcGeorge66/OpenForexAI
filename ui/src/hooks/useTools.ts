/**
 * useTools — loads the tool list once from GET /tools.
 */

import { useEffect, useState } from 'react'
import { api, type ToolInfo } from '@/api/client'

export function useTools() {
  const [tools, setTools] = useState<ToolInfo[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let active = true
    api.getTools()
      .then(data => { if (active) { setTools(data.tools); setError(null) } })
      .catch(err => { if (active) setError(String(err)) })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [])

  return { tools, loading, error }
}
