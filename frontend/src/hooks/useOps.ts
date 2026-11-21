import { useCallback, useEffect, useState } from 'react'
import { api } from '../api/client'
import type { Depot, DispatchTask, Health, MemoryFact, Route, Team } from '../types/api'

export interface OpsData {
  health: Health | null
  depots: Depot[]
  routes: Route[]
  teams: Team[]
  tasks: DispatchTask[]
  memory: MemoryFact[]
}

const EMPTY: OpsData = { health: null, depots: [], routes: [], teams: [], tasks: [], memory: [] }

export function useOps(pollMs = 15000) {
  const [data, setData] = useState<OpsData>(EMPTY)
  const [offline, setOffline] = useState(false)

  const refresh = useCallback(async () => {
    try {
      const [health, depots, routes, teams, tasks, memory] = await Promise.all([
        api.health(),
        api.depots(),
        api.routes(),
        api.teams(),
        api.tasks(),
        api.memory(),
      ])
      setData({ health, depots, routes, teams, tasks, memory })
      setOffline(false)
    } catch {
      setOffline(true)
    }
  }, [])

  useEffect(() => {
    // Initial load from the API (an external system), then poll.
    // oxlint-disable-next-line react/set-state-in-effect
    void refresh()
    const id = window.setInterval(refresh, pollMs)
    return () => window.clearInterval(id)
  }, [refresh, pollMs])

  return { ...data, offline, refresh }
}
