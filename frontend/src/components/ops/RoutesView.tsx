import { minutes, wardName } from '../../lib/format'
import type { Route, RouteStatus } from '../../types/api'

const STYLE: Record<RouteStatus, string> = {
  open: 'bg-bank-wash text-bank',
  slow: 'bg-flood-wash text-[#7a5800]',
  blocked: 'bg-signal-wash text-signal',
}

interface Props {
  routes: Route[]
  onChange: (id: string, status: RouteStatus) => void
}

export function RoutesView({ routes, onChange }: Props) {
  return (
    <ul className="divide-y divide-silt-deep">
      {routes.map((r) => (
        <li key={r.id} className="flex items-start justify-between gap-3 py-2.5">
          <div>
            <p className="font-semibold">
              {r.name} <span className="font-normal text-ink-soft">{r.id}</span>
            </p>
            <p className="text-sm text-ink-soft">
              {r.depot_id} to {wardName(r.ward_id)}, {minutes(r.travel_minutes)} by {r.vehicle}
            </p>
            {r.note && <p className="text-sm">{r.note}</p>}
          </div>
          <label className="shrink-0">
            <span className="sr-only">Status of {r.name}</span>
            <select
              value={r.status}
              onChange={(e) => onChange(r.id, e.target.value as RouteStatus)}
              className={`rounded px-2 py-1 text-sm font-semibold ${STYLE[r.status]}`}
            >
              <option value="open">Open</option>
              <option value="slow">Slow</option>
              <option value="blocked">Blocked</option>
            </select>
          </label>
        </li>
      ))}
    </ul>
  )
}
