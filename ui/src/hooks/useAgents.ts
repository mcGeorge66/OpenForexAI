/**
 * useAgents — polls GET /agents every 10 seconds.
 */

import { useEffect, useState } from 'react'
import { api, type AgentInfo } from '@/api/client'

export function useAgents(intervalMs = 10_000) {
  const [agents, setAgents] = useState<AgentInfo[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let active = true

    async function fetch() {
      try {
        const data = await api.getAgents()
        if (active) {
          setAgents(data)
          setError(null)
        }
      } catch (err) {
        if (active) setError(String(err))
      } finally {
        if (active) setLoading(false)
      }
    }

    fetch()
    const timer = setInterval(fetch, intervalMs)
    return () => {
      active = false
      clearInterval(timer)
    }
  }, [intervalMs])

  return { agents, loading, error }
}
