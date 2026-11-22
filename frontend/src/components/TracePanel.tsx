import { useEffect, useRef } from 'react'
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
  const listRef = useRef<HTMLOListElement>(null)
  // Follow new steps while the reader is at the bottom; leave them alone if they scrolled up.
  const followRef = useRef(true)

  useEffect(() => {
    const el = listRef.current
    if (el && followRef.current) el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' })
  }, [trace])

  const onScroll = () => {
    const el = listRef.current
    if (el) followRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < 48
  }

  return (
    <section className="panel panel-tall flex flex-col" aria-label="Agent reasoning">
      <div className="flex shrink-0 items-baseline justify-between gap-3 border-b border-silt-deep px-4 py-3">
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
        <ol ref={listRef} onScroll={onScroll} className="waterline min-h-0 flex-1 space-y-5 overflow-y-auto px-4 py-5">
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
                      <ResultBadge name={call.name} result={call.result} />
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

const DISPATCH_TOOL = 'create_dispatch_task'

/** Status of one tool call. A coordinator's decision on a dispatch is not a tool fault. */
function ResultBadge({ name, result }: { name: string; result?: { ok: boolean; error?: string | null } }) {
  if (!result) {
    const label = name === DISPATCH_TOOL ? 'awaiting approval' : 'running'
    return <span className="text-xs text-ink-soft">{label}</span>
  }
  if (result.ok) return <span className="text-xs font-semibold text-bank">done</span>
  if (name === DISPATCH_TOOL && result.error?.startsWith('Coordinator asked for a revised plan')) {
    return <span className="text-xs font-semibold text-[#7a5800]">sent back</span>
  }
  if (name === DISPATCH_TOOL && result.error?.startsWith('Coordinator rejected')) {
    return <span className="text-xs font-semibold text-signal">rejected</span>
  }
  return <span className="text-xs font-semibold text-signal">problem</span>
}
