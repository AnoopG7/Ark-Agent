import { useCallback } from 'react'
import { api } from './api/client'
import { ChatPanel } from './components/ChatPanel'
import { Header } from './components/Header'
import { OpsPanel } from './components/OpsPanel'
import { TracePanel } from './components/TracePanel'
import { useAgentThread } from './hooks/useAgentThread'
import { useOps } from './hooks/useOps'
import type { RouteStatus } from './types/api'

export default function App() {
  const ops = useOps()
  const agent = useAgentThread(ops.refresh)

  const changeRoute = useCallback(
    async (id: string, status: RouteStatus) => {
      await api.updateRoute(id, status)
      await ops.refresh()
    },
    [ops],
  )

  // A fresh demo world: seed stock, routes and teams, no dispatches, and no remembered facts
  // about dispatches that no longer exist.
  const reset = useCallback(async () => {
    await Promise.all([api.reset(), api.clearMemory()])
    agent.newConversation()
    await ops.refresh()
  }, [agent, ops])

  const clearMemory = useCallback(async () => {
    await api.clearMemory()
    await ops.refresh()
  }, [ops])

  return (
    <div className="mx-auto max-w-[1600px] space-y-5 px-4 py-5 lg:px-6">
      <Header
        health={ops.health}
        offline={ops.offline}
        onReset={reset}
        onNewConversation={agent.newConversation}
      />
      <main className="grid gap-5 lg:grid-cols-2 xl:grid-cols-[1.05fr_1fr_1fr]">
        <ChatPanel
          chat={agent.chat}
          pending={agent.pending}
          running={agent.running}
          error={agent.error}
          onSend={agent.send}
          onDecide={agent.decide}
        />
        <TracePanel trace={agent.trace} status={agent.status} />
        <div className="lg:col-span-2 xl:col-span-1">
          <OpsPanel data={ops} onRouteChange={changeRoute} onClearMemory={clearMemory} />
        </div>
      </main>
    </div>
  )
}
