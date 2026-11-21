import { useEffect, useRef, useState } from 'react'
import { api } from '../../api/client'

/** Renders the LangGraph structure served by the backend (GET /api/graph). */
export function GraphView() {
  const ref = useRef<HTMLDivElement>(null)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const [{ mermaid: source }, { default: mermaid }] = await Promise.all([api.graph(), import('mermaid')])
        mermaid.initialize({
          startOnLoad: false,
          theme: 'base',
          themeVariables: {
            primaryColor: '#d6e9ea',
            primaryBorderColor: '#1f6f78',
            lineColor: '#46606f',
            fontFamily: 'Public Sans Variable, sans-serif',
          },
        })
        const { svg } = await mermaid.render('ark-graph', source)
        if (!cancelled && ref.current) ref.current.innerHTML = svg
      } catch {
        if (!cancelled) setFailed(true)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [])

  return (
    <div className="space-y-3">
      <p className="text-sm text-ink-soft">
        The planning loop: Ark reasons, calls tools and repeats until it can propose a dispatch,
        which always stops at your approval. Dashed arrows are decisions.
      </p>
      {failed ? <p className="text-signal">Could not load the graph diagram.</p> : <div ref={ref} className="[&_svg]:mx-auto [&_svg]:max-w-full" />}
    </div>
  )
}
