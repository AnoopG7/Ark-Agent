import type { TraceStep } from '../hooks/useAgentThread'
import { describeArgs, describeResult, toolLabel } from '../lib/toolSummary'
import type { RunStatus } from '../types/api'

const STATUS_TEXT: Partial<Record<RunStatus, string>> = {
  running: 'Reasoning…',
  awaiting_approval: 'Waiting for your decision',
  dispatched: 'Dispatched',
  rejected: 'Rejected',
  answered: 'Answered',
  step_limit: 'Stopped at the step limit',
}

interface Props {
  trace: TraceStep[]
  status: RunStatus
  maxSteps?: number
}

export function TracePanel({ trace, status, maxSteps = 8 }: Props) {
  return (
    <section className="panel flex min-h-[32rem] flex-col" aria-label="Agent reasoning">
      <div className="flex items-baseline justify-between border-b border-silt-deep px-4 py-3">
        <h2 className="display text-lg font-[650]">How Ark is planning</h2>
        <span className="text-sm text-ink-soft tabular" aria-live="polite">
          {trace.length > 0 && `Step ${trace.length} of ${maxSteps}. `}
          {STATUS_TEXT[status] ?? ''}
        </span>
      </div>

      {trace.length === 0 ? (
        <p className="px-4 py-6 text-ink-soft">
          Each step appears here as Ark reasons, calls a tool and reads the result.
        </p>
      ) : (
        <ol className="waterline flex-1 space-y-5 overflow-y-auto px-4 py-5">
          {trace.map((step) => (
            <li key={step.step} className="relative pl-11">
              <span
                className="absolute left-0 top-0 grid size-8 place-items-center rounded-full border-2 border-river bg-paper text-sm font-semibold text-river tabular"
                aria-hidden
              >
                {step.step}
              </span>
              {step.thought && (
                <p className="mb-2 text-sm italic text-ink-soft">{step.thought.replace(/^Thought:\s*/i, '')}</p>
              )}
              <ul className="space-y-2">
                {step.calls.map((call) => (
                  <li key={call.id} className="rounded-md bg-white px-3 py-2 ring-1 ring-silt-deep">
                    <div className="flex items-baseline justify-between gap-3">
                      <span className="font-semibold">{toolLabel(call.name)}</span>
                      <ResultBadge result={call.result} />
                    </div>
                    <p className="text-sm text-ink-soft">{describeArgs(call.name, call.args)}</p>
                    {call.result && (
                      <p
                        className={`mt-1 text-sm ${call.result.ok ? 'text-ink' : 'text-signal'}`}
                      >
                        {call.result.ok ? describeResult(call.name, call.result.data) : call.result.error}
                      </p>
                    )}
                  </li>
                ))}
              </ul>
            </li>
          ))}
        </ol>
      )}
    </section>
  )
}

function ResultBadge({ result }: { result?: { ok: boolean } }) {
  if (!result) return <span className="text-xs text-ink-soft">running</span>
  return result.ok ? (
    <span className="text-xs font-semibold text-bank">done</span>
  ) : (
    <span className="text-xs font-semibold text-signal">problem</span>
  )
}
