import { type FormEvent, type KeyboardEvent, useEffect, useRef, useState } from 'react'
import type { ChatLine } from '../hooks/useAgentThread'
import type { Decision, PendingApproval } from '../types/api'
import { plainText } from '../lib/format'
import { ApprovalSlip } from './ApprovalSlip'

const EXAMPLES = [
  'Ward 7 needs drinking water for 300 people by evening',
  'Ward 9 needs drinking water for 120 people, roads are flooded',
  'Ward 12 needs medicine kits for 2,000 people',
]

interface Props {
  chat: ChatLine[]
  pending: PendingApproval | null
  running: boolean
  error: string | null
  onSend: (text: string) => void
  onDecide: (decision: Decision, note: string) => void
}

export function ChatPanel({ chat, pending, running, error, onSend, onDecide }: Props) {
  const [text, setText] = useState('')
  const endRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)

  // Grow the request box with its text (up to about six lines, then it scrolls).
  useEffect(() => {
    const el = inputRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`
  }, [text])

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [chat.length, pending])

  const submit = (e: FormEvent) => {
    e.preventDefault()
    const value = text.trim()
    if (!value || running || pending) return
    onSend(value)
    setText('')
  }

  // Enter sends; Shift+Enter adds a new line.
  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) submit(e)
  }

  return (
    <section className="panel panel-tall flex flex-col" aria-label="Conversation">
      <h2 className="display shrink-0 border-b border-silt-deep px-4 py-3 text-lg font-[650]">Requests</h2>

      <div className="min-h-0 flex-1 space-y-3 overflow-y-auto px-4 py-4">
        {chat.length === 0 && (
          <div className="space-y-3">
            <p className="text-ink-soft">
              Describe what a ward needs. Ark checks stock, roads and teams, then asks you before
              sending anyone.
            </p>
            <ul className="space-y-2">
              {EXAMPLES.map((ex) => (
                <li key={ex}>
                  <button
                    type="button"
                    className="w-full rounded-md border border-silt-deep bg-white px-3 py-2 text-left text-sm hover:border-river"
                    onClick={() => setText(ex)}
                  >
                    {ex}
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}

        {chat.map((line, i) => (
          <div
            key={i}
            className={
              line.role === 'user'
                ? 'ml-8 rounded-lg bg-river px-3 py-2 text-white'
                : line.role === 'system'
                  ? 'text-center text-sm text-ink-soft'
                  : 'mr-8 whitespace-pre-wrap rounded-lg bg-white px-3 py-2 ring-1 ring-silt-deep'
            }
          >
            {line.role === 'assistant' ? plainText(line.text) : line.text}
          </div>
        ))}

        {running && !pending && <p className="text-sm text-ink-soft">Ark is working on it…</p>}
        {pending && <ApprovalSlip pending={pending} busy={running} onDecide={onDecide} />}
        {error && (
          <p role="alert" className="rounded bg-signal-wash px-3 py-2 text-sm text-signal">
            {error}
          </p>
        )}
        <div ref={endRef} />
      </div>

      <form onSubmit={submit} className="flex shrink-0 items-end gap-2 border-t border-silt-deep p-3">
        <label htmlFor="request" className="sr-only">
          Relief request
        </label>
        <textarea
          id="request"
          ref={inputRef}
          rows={1}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder={pending ? 'Decide on the dispatch above first' : 'Ward 7 needs drinking water for 300 people'}
          disabled={Boolean(pending)}
          maxLength={2000}
          className="min-w-0 flex-1 resize-none overflow-y-auto rounded-md border border-silt-deep bg-white px-3 py-2 leading-snug break-words disabled:bg-silt"
        />
        <button type="submit" className="btn btn-primary" disabled={running || !text.trim() || Boolean(pending)}>
          Send
        </button>
      </form>
    </section>
  )
}
