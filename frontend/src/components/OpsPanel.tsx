import { useState } from 'react'
import type { OpsData } from '../hooks/useOps'
import type { RouteStatus } from '../types/api'
import { DepotsView } from './ops/DepotsView'
import { GraphView } from './ops/GraphView'
import { MemoryView } from './ops/MemoryView'
import { RoutesView } from './ops/RoutesView'
import { TasksView } from './ops/TasksView'
import { TeamsView } from './ops/TeamsView'

const TABS = ['Depots', 'Roads', 'Teams', 'Dispatches', 'Memory', 'Graph'] as const
type Tab = (typeof TABS)[number]

interface Props {
  data: OpsData
  onRouteChange: (id: string, status: RouteStatus) => void
  onClearMemory: () => void
}

export function OpsPanel({ data, onRouteChange, onClearMemory }: Props) {
  const [tab, setTab] = useState<Tab>('Depots')
  const blocked = data.routes.filter((r) => r.status === 'blocked').length

  return (
    <section className="panel flex min-h-[32rem] flex-col" aria-label="Operations">
      <div role="tablist" className="flex flex-wrap gap-1 border-b border-silt-deep px-2 pt-2">
        {TABS.map((t) => (
          <button
            key={t}
            role="tab"
            type="button"
            aria-selected={tab === t}
            onClick={() => setTab(t)}
            className={`rounded-t-md px-3 py-2 text-sm font-semibold ${
              tab === t ? 'bg-white text-ink ring-1 ring-silt-deep' : 'text-ink-soft hover:text-ink'
            }`}
          >
            {t}
            {t === 'Roads' && blocked > 0 && (
              <span className="ml-1.5 rounded-full bg-signal px-1.5 text-xs text-white tabular">{blocked}</span>
            )}
            {t === 'Dispatches' && data.tasks.length > 0 && (
              <span className="ml-1.5 text-ink-soft tabular">{data.tasks.length}</span>
            )}
          </button>
        ))}
      </div>
      <div role="tabpanel" className="flex-1 overflow-y-auto p-4">
        {tab === 'Depots' && <DepotsView depots={data.depots} />}
        {tab === 'Roads' && <RoutesView routes={data.routes} onChange={onRouteChange} />}
        {tab === 'Teams' && <TeamsView teams={data.teams} />}
        {tab === 'Dispatches' && <TasksView tasks={data.tasks} />}
        {tab === 'Memory' && <MemoryView facts={data.memory} onClear={onClearMemory} />}
        {tab === 'Graph' && <GraphView />}
      </div>
    </section>
  )
}
