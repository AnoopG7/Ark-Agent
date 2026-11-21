import { useState } from 'react'
import { RESOURCE_LABEL, minutes, num, qty, wardName } from '../lib/format'
import type { Decision, PendingApproval } from '../types/api'

interface Props {
  pending: PendingApproval
  busy: boolean
  onDecide: (decision: Decision, note: string) => void
}

/** The coordinator's approval checkpoint, styled as a dispatch slip. */
export function ApprovalSlip({ pending, busy, onDecide }: Props) {
  const [note, setNote] = useState('')
  const plan = pending.plan
  const reviseBlocked = !note.trim()

  return (
    <section
      aria-labelledby="slip-title"
      className="slip-enter overflow-hidden rounded-[var(--radius-slip)] border border-flood bg-white shadow-[0_1px_0_var(--color-flood),0_8px_24px_-12px_rgba(15,42,61,0.35)]"
    >
      <div className="flex items-center justify-between gap-3 bg-flood px-4 py-2 text-ink">
        <h2 id="slip-title" className="display text-base font-[700]">
          Dispatch awaiting your approval
        </h2>
        <span className="text-sm font-semibold tabular">{wardName(plan.ward_id)}</span>
      </div>

      <div className="space-y-4 p-4">
        <p className="display text-xl font-[650] leading-snug">
          {qty(plan.total_allocated, plan.resource)} of {RESOURCE_LABEL[plan.resource].toLowerCase()} for{' '}
          {num(plan.people)} people
        </p>

        <table className="w-full text-sm tabular">
          <thead className="text-left text-ink-soft">
            <tr>
              <th className="pb-1 font-medium">From</th>
              <th className="pb-1 font-medium">Route</th>
              <th className="pb-1 text-right font-medium">Quantity</th>
            </tr>
          </thead>
          <tbody>
            {plan.allocations.map((a) => (
              <tr key={a.depot_id} className="border-t border-dashed border-silt-deep">
                <td className="py-1.5">{a.depot_id}</td>
                <td className="py-1.5">{a.route_id}</td>
                <td className="py-1.5 text-right">{qty(a.quantity, a.resource)}</td>
              </tr>
            ))}
          </tbody>
        </table>

        <dl className="grid grid-cols-3 gap-3 text-sm">
          <div>
            <dt className="text-ink-soft">Team</dt>
            <dd className="font-semibold">{plan.team_id}</dd>
          </div>
          <div>
            <dt className="text-ink-soft">Arrives in</dt>
            <dd className="font-semibold tabular">{minutes(plan.eta_minutes)}</dd>
          </div>
          <div>
            <dt className="text-ink-soft">Needed</dt>
            <dd className="font-semibold tabular">{qty(plan.quantity_required, plan.resource)}</dd>
          </div>
        </dl>

        {plan.shortfall > 0 && (
          <p className="rounded bg-signal-wash px-3 py-2 text-sm text-signal">
            Short by {qty(plan.shortfall, plan.resource)}. Approving sends what is available.
          </p>
        )}

        <p className="text-sm leading-relaxed">{plan.rationale}</p>
        {plan.citations.length > 0 && (
          <p className="text-xs text-ink-soft">Based on {plan.citations.join(', ')}</p>
        )}

        <label className="block text-sm">
          <span className="text-ink-soft">Note for the record (required to send back)</span>
          <input
            value={note}
            onChange={(e) => setNote(e.target.value)}
            maxLength={500}
            className="mt-1 w-full rounded border border-silt-deep px-3 py-2"
            placeholder="e.g. Use the Harbour depot first"
          />
        </label>

        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            className="btn btn-primary"
            disabled={busy}
            onClick={() => onDecide('approve', note)}
          >
            Approve dispatch
          </button>
          <button
            type="button"
            className="btn btn-quiet"
            disabled={busy || reviseBlocked}
            title={reviseBlocked ? 'Write a note explaining what to change' : undefined}
            onClick={() => onDecide('revise', note)}
          >
            Send back with note
          </button>
          <button
            type="button"
            className="btn btn-danger"
            disabled={busy}
            onClick={() => onDecide('reject', note)}
          >
            Reject
          </button>
        </div>
      </div>
    </section>
  )
}
