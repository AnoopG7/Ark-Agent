import { qty, timeAgo, wardName } from '../../lib/format'
import type { DispatchTask } from '../../types/api'

export function TasksView({ tasks }: { tasks: DispatchTask[] }) {
  if (!tasks.length) return <p className="text-ink-soft">No dispatch decisions yet.</p>
  return (
    <ul className="space-y-3">
      {tasks.map((t) => (
        <li key={t.id} className="rounded-md bg-white px-3 py-2 ring-1 ring-silt-deep">
          <div className="flex items-baseline justify-between">
            <span className="font-semibold">
              {t.id}, {wardName(t.plan.ward_id)}
            </span>
            <span className={`text-sm font-semibold ${t.status === 'dispatched' ? 'text-bank' : 'text-signal'}`}>
              {t.status === 'dispatched' ? 'Dispatched' : 'Rejected'}
            </span>
          </div>
          <p className="text-sm">
            {qty(t.plan.total_allocated, t.plan.resource)} with team {t.plan.team_id}
          </p>
          <p className="text-xs text-ink-soft">
            {timeAgo(t.created_at)}
            {t.decision_note && `. Note: ${t.decision_note}`}
          </p>
        </li>
      ))}
    </ul>
  )
}
