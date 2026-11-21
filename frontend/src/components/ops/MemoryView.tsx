import { humanize, timeAgo, wardName } from '../../lib/format'
import type { MemoryFact } from '../../types/api'

interface Props {
  facts: MemoryFact[]
  onClear: () => void
}

export function MemoryView({ facts, onClear }: Props) {
  return (
    <div className="space-y-3">
      <div className="flex items-baseline justify-between gap-3">
        <p className="text-sm text-ink-soft">
          What Ark remembers across conversations and shifts. It reads these before planning.
        </p>
        {facts.length > 0 && (
          <button type="button" className="btn btn-danger shrink-0" onClick={onClear}>
            Clear memory
          </button>
        )}
      </div>
      {facts.length === 0 ? (
        <p className="text-ink-soft">Nothing remembered yet. Approved dispatches are recorded here.</p>
      ) : (
        <ul className="space-y-2">
          {facts.map((f) => (
            <li key={f.id} className="border-l-2 border-river pl-3">
              <p className="text-sm">{f.content}</p>
              <p className="text-xs text-ink-soft">
                {humanize(f.kind)}
                {f.ward_id && `, ${wardName(f.ward_id)}`}, {timeAgo(f.created_at)}
              </p>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
