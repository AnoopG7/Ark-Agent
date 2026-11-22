import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError, api } from '../api/client'
import type { AgentEvent, ChatMessage, Decision, PendingApproval, RunStatus } from '../types/api'

export interface TraceCall {
  id: string
  name: string
  args: Record<string, unknown>
  result?: { ok: boolean; data?: unknown; error?: string | null }
}

export interface TraceStep {
  step: number
  thought?: string
  calls: TraceCall[]
}

export interface ChatLine {
  role: 'user' | 'assistant' | 'system'
  text: string
}

const STORAGE_KEY = 'ark.threadId'

/** Rebuild the chat and the current request's trace from persisted thread messages. */
function fromHistory(messages: ChatMessage[]): { chat: ChatLine[]; trace: TraceStep[] } {
  const chat: ChatLine[] = []
  let trace: TraceStep[] = []
  const byCall = new Map<string, TraceCall>()
  for (const m of messages) {
    if (m.role === 'user') {
      chat.push({ role: 'user', text: m.content })
      trace = []
      byCall.clear()
    } else if (m.role === 'assistant' && m.tool_calls.length) {
      const calls = m.tool_calls.map((c) => ({ ...c }))
      calls.forEach((c) => byCall.set(c.id, c))
      trace.push({ step: trace.length + 1, thought: m.content || undefined, calls })
    } else if (m.role === 'assistant' && m.content) {
      chat.push({ role: 'assistant', text: m.content })
    } else if (m.role === 'tool' && m.tool_call_id) {
      const call = byCall.get(m.tool_call_id)
      if (call) {
        try {
          call.result = JSON.parse(m.content)
        } catch {
          call.result = { ok: Boolean(m.ok), data: m.content }
        }
      }
    }
  }
  return { chat, trace }
}

export function useAgentThread(onRunFinished: () => void) {
  const [threadId, setThreadId] = useState<string | null>(() => localStorage.getItem(STORAGE_KEY))
  const [chat, setChat] = useState<ChatLine[]>([])
  const [trace, setTrace] = useState<TraceStep[]>([])
  const [pending, setPending] = useState<PendingApproval | null>(null)
  const [status, setStatus] = useState<RunStatus>('new')
  const [running, setRunning] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const finished = useRef(onRunFinished)
  useEffect(() => {
    finished.current = onRunFinished
  }, [onRunFinished])

  // Threads created in this session start empty and are filled by the live stream; only a
  // thread restored from localStorage needs its history fetched. Re-fetching a fresh thread
  // would race the stream and wipe the message that was just sent.
  const createdHere = useRef(new Set<string>())

  useEffect(() => {
    if (!threadId || createdHere.current.has(threadId)) return
    let stale = false
    api
      .getThread(threadId)
      .then((state) => {
        if (stale) return
        const { chat: c, trace: t } = fromHistory(state.messages)
        setChat(c)
        setTrace(t)
        setPending(state.pending_approval)
        setStatus(state.status)
      })
      .catch(() => undefined)
    return () => {
      stale = true
    }
  }, [threadId])

  const ensureThread = useCallback(async () => {
    if (threadId) return threadId
    const { thread_id } = await api.createThread()
    createdHere.current.add(thread_id)
    localStorage.setItem(STORAGE_KEY, thread_id)
    setThreadId(thread_id)
    return thread_id
  }, [threadId])

  const handle = useCallback((event: AgentEvent) => {
    switch (event.type) {
      case 'thought':
        setTrace((t) => upsertStep(t, event.step, (s) => ({ ...s, thought: event.data.text })))
        break
      case 'tool_call':
        setTrace((t) =>
          upsertStep(t, event.step, (s) => ({ ...s, calls: [...s.calls, { ...event.data }] })),
        )
        break
      case 'tool_result':
        setTrace((t) =>
          t.map((s) => ({
            ...s,
            calls: s.calls.map((c) =>
              c.id === event.data.tool_call_id
                ? { ...c, result: { ok: event.data.ok, data: event.data.data, error: event.data.error } }
                : c,
            ),
          })),
        )
        break
      case 'interrupt':
        setPending(event.data)
        break
      case 'answer':
        setChat((c) => [...c, { role: 'assistant', text: event.data.text }])
        break
      case 'done':
        setStatus(event.data.status)
        if (event.data.status !== 'awaiting_approval') setPending(null)
        break
      case 'error':
        setError(event.data.message)
        break
    }
  }, [])

  const run = useCallback(
    async (work: () => Promise<void>) => {
      setRunning(true)
      setError(null)
      setStatus('running')
      try {
        await work()
      } catch (e) {
        setError(e instanceof ApiError ? e.message : 'Lost connection to the planning service.')
      } finally {
        setRunning(false)
        finished.current()
      }
    },
    [],
  )

  const send = useCallback(
    (text: string) =>
      run(async () => {
        const id = await ensureThread()
        setChat((c) => [...c, { role: 'user', text }])
        setTrace([])
        await api.sendMessage(id, text, handle)
      }),
    [ensureThread, handle, run],
  )

  const decide = useCallback(
    (decision: Decision, note: string) =>
      run(async () => {
        if (!threadId) return
        setPending(null)
        const verb = { approve: 'Approved', reject: 'Rejected', revise: 'Sent back for revision' }[decision]
        setChat((c) => [...c, { role: 'system', text: note ? `${verb}: ${note}` : verb }])
        await api.resume(threadId, decision, note, handle)
      }),
    [handle, run, threadId],
  )

  const newConversation = useCallback(() => {
    localStorage.removeItem(STORAGE_KEY)
    setThreadId(null)
    setChat([])
    setTrace([])
    setPending(null)
    setStatus('new')
    setError(null)
  }, [])

  return { threadId, chat, trace, pending, status, running, error, send, decide, newConversation }
}

function upsertStep(steps: TraceStep[], step: number, update: (s: TraceStep) => TraceStep) {
  const existing = steps.find((s) => s.step === step)
  if (existing) return steps.map((s) => (s.step === step ? update(s) : s))
  return [...steps, update({ step, calls: [] })]
}
