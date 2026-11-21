import type { Health } from '../types/api'

interface Props {
  health: Health | null
  offline: boolean
  onReset: () => void
  onNewConversation: () => void
}

function Signal({ ok, label }: { ok: boolean; label: string }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-sm text-ink-soft">
      <span className={`size-2 rounded-full ${ok ? 'bg-bank' : 'bg-signal'}`} aria-hidden />
      {label}
    </span>
  )
}

export function Header({ health, offline, onReset, onNewConversation }: Props) {
  return (
    <header className="flex flex-wrap items-end justify-between gap-4 border-b border-silt-deep pb-4">
      <div>
        <h1 className="display text-3xl font-[750] leading-none text-ink">Ark</h1>
        <p className="mt-1 text-ink-soft">Driftwood Bay Flood Relief Coordination Centre</p>
      </div>
      <div className="flex flex-wrap items-center gap-x-5 gap-y-2">
        {offline ? (
          <Signal ok={false} label="Planning service unreachable" />
        ) : (
          <>
            <Signal ok={Boolean(health?.database)} label="Database" />
            <Signal
              ok={Boolean(health?.llm_configured)}
              label={health?.llm_configured ? health.model : 'No Groq API key'}
            />
          </>
        )}
        <button type="button" className="btn btn-quiet" onClick={onNewConversation}>
          New conversation
        </button>
        <button type="button" className="btn btn-quiet" onClick={onReset}>
          Reset demo data
        </button>
      </div>
    </header>
  )
}
