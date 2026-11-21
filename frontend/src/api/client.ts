import type {
  AgentEvent,
  Decision,
  Depot,
  DispatchTask,
  Health,
  MemoryFact,
  Route,
  RouteStatus,
  Team,
  ThreadState,
  Ward,
} from '../types/api'

export class ApiError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...init?.headers },
  })
  if (!res.ok) throw new ApiError(res.status, await errorText(res))
  if (res.status === 204) return undefined as T
  return (await res.json()) as T
}

async function errorText(res: Response): Promise<string> {
  try {
    const body = await res.json()
    if (typeof body.detail === 'string') return body.detail
    if (Array.isArray(body.detail)) return body.detail.map((d: { msg: string }) => d.msg).join('; ')
  } catch {
    /* fall through */
  }
  return `Request failed with status ${res.status}`
}

/** POST a body and read the Server-Sent Events stream, calling onEvent for every frame. */
async function streamEvents(
  path: string,
  body: unknown,
  onEvent: (event: AgentEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetch(`/api${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
    body: JSON.stringify(body),
    signal,
  })
  if (!res.ok || !res.body) throw new ApiError(res.status, await errorText(res))

  const reader = res.body.pipeThrough(new TextDecoderStream()).getReader()
  let buffer = ''
  for (;;) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += value
    let boundary = buffer.indexOf('\n\n')
    while (boundary !== -1) {
      const frame = buffer.slice(0, boundary)
      buffer = buffer.slice(boundary + 2)
      const data = frame
        .split('\n')
        .filter((line) => line.startsWith('data: '))
        .map((line) => line.slice(6))
        .join('\n')
      if (data) onEvent(JSON.parse(data) as AgentEvent)
      boundary = buffer.indexOf('\n\n')
    }
  }
}

export const api = {
  health: () => request<Health>('/health'),
  createThread: () => request<{ thread_id: string }>('/threads', { method: 'POST' }),
  getThread: (id: string) => request<ThreadState>(`/threads/${id}`),
  sendMessage: (id: string, content: string, onEvent: (e: AgentEvent) => void, signal?: AbortSignal) =>
    streamEvents(`/threads/${id}/messages`, { content }, onEvent, signal),
  resume: (id: string, decision: Decision, note: string, onEvent: (e: AgentEvent) => void) =>
    streamEvents(`/threads/${id}/resume`, { decision, note }, onEvent),

  wards: () => request<Ward[]>('/ops/wards'),
  depots: () => request<Depot[]>('/ops/depots'),
  routes: () => request<Route[]>('/ops/routes'),
  teams: () => request<Team[]>('/ops/teams'),
  tasks: () => request<DispatchTask[]>('/ops/tasks'),
  updateRoute: (id: string, status: RouteStatus, note?: string) =>
    request<Route>(`/ops/routes/${id}`, { method: 'PATCH', body: JSON.stringify({ status, note }) }),
  reset: () => request<void>('/ops/reset', { method: 'POST' }),

  memory: () => request<MemoryFact[]>('/memory'),
  clearMemory: () => request<{ deleted: number }>('/memory', { method: 'DELETE' }),
  graph: () => request<{ mermaid: string }>('/graph'),
}
