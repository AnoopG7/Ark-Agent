import { RESOURCE_LABEL, num } from '../../lib/format'
import type { Depot } from '../../types/api'

export function DepotsView({ depots }: { depots: Depot[] }) {
  return (
    <div className="space-y-5">
      {depots.map((depot) => (
        <article key={depot.id}>
          <h3 className="font-semibold">
            {depot.name} <span className="font-normal text-ink-soft">{depot.id}</span>
          </h3>
          <ul className="mt-2 space-y-1.5">
            {depot.stock.map((item) => {
              const reservedPct = item.quantity ? (item.reserved / item.quantity) * 100 : 0
              return (
                <li key={item.resource} className="grid grid-cols-[8.5rem_1fr_4.5rem] items-center gap-2 text-sm">
                  <span>{RESOURCE_LABEL[item.resource]}</span>
                  <span
                    className="h-2 overflow-hidden rounded-full bg-river"
                    role="img"
                    aria-label={`${item.reserved} of ${item.quantity} reserved`}
                  >
                    <span className="block h-full bg-flood" style={{ width: `${reservedPct}%` }} />
                  </span>
                  <span className="text-right tabular">{num(item.available)}</span>
                </li>
              )
            })}
          </ul>
        </article>
      ))}
      <p className="text-xs text-ink-soft">
        Bars show stock on hand; the amber part is reserved by approved dispatches. Numbers are
        what is still available.
      </p>
    </div>
  )
}
