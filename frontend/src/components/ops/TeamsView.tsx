import { humanize } from '../../lib/format'
import type { Team } from '../../types/api'

const STATUS_CLASS = {
  available: 'text-bank',
  deployed: 'text-[#7a5800]',
  resting: 'text-ink-soft',
}

export function TeamsView({ teams }: { teams: Team[] }) {
  return (
    <ul className="divide-y divide-silt-deep">
      {teams.map((t) => (
        <li key={t.id} className="flex items-start justify-between gap-3 py-2.5">
          <div>
            <p className="font-semibold">
              {t.name} <span className="font-normal text-ink-soft">{t.id}</span>
            </p>
            <p className="text-sm text-ink-soft">
              {t.skills.map(humanize).join(', ')}. {t.size} people, {t.vehicle}, based at {t.base_depot}
            </p>
          </div>
          <span className={`text-sm font-semibold ${STATUS_CLASS[t.status]}`}>{humanize(t.status)}</span>
        </li>
      ))}
    </ul>
  )
}
