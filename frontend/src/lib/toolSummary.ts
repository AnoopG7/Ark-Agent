import type { ResourceType } from '../types/api'
import { humanize, qty, wardName } from './format'

type Json = Record<string, unknown>

const TOOL_LABEL: Record<string, string> = {
  situation_report: 'Situation report',
  stock_lookup: 'Check stock',
  road_status: 'Check roads',
  list_teams: 'Find teams',
  search_guidelines: 'Search guidelines',
  recall_facts: 'Recall memory',
  remember_fact: 'Save to memory',
  create_dispatch_task: 'Propose dispatch',
}

export function toolLabel(name: string): string {
  return TOOL_LABEL[name] ?? humanize(name)
}

/** One line describing what the agent asked for. */
export function describeArgs(name: string, args: Json): string {
  switch (name) {
    case 'situation_report':
      return `${humanize(String(args.resource ?? ''))} for ${wardName(String(args.ward_id ?? ''))}`
    case 'stock_lookup':
      return `${humanize(String(args.resource ?? ''))}${args.depot_id ? ` at ${args.depot_id}` : ', all depots'}`
    case 'road_status':
      return args.ward_id ? `Routes to ${wardName(String(args.ward_id))}` : `Route ${args.route_id ?? 'all'}`
    case 'list_teams':
      return [args.skill && humanize(String(args.skill)), args.status ?? 'available']
        .filter(Boolean)
        .join(', ')
    case 'search_guidelines':
      return `“${args.query}”`
    case 'create_dispatch_task':
      return `${wardName(String(args.ward_id))}, team ${args.team_id}`
    case 'remember_fact':
      return String(args.content ?? '')
    case 'recall_facts':
      return args.ward_id ? wardName(String(args.ward_id)) : 'All wards'
    default:
      return JSON.stringify(args)
  }
}

/** One line describing what the tool returned. */
export function describeResult(name: string, data: unknown): string {
  const d = (data ?? {}) as Json
  switch (name) {
    case 'situation_report': {
      const resource = d.resource as ResourceType
      const routes = ((d.routes as Json[]) ?? []).map((x) => `${x.id} ${x.status}`)
      const teams = ((d.available_teams as Json[]) ?? []).map((t) => t.id)
      return [
        `${qty(Number(d.total_available ?? 0), resource)} available`,
        routes.length ? `routes ${routes.join(', ')}` : String(d.message ?? 'no routes'),
        teams.length ? `teams ${teams.join(', ')}` : 'no available team',
      ].join('. ')
    }
    case 'stock_lookup': {
      const depots = (d.depots as Json[]) ?? []
      const resource = d.resource as ResourceType
      const parts = depots.map((x) => `${String(x.depot_id).replace('DEP-', '')} ${x.available}`)
      return `${qty(Number(d.total_available ?? 0), resource)} available (${parts.join(', ')})`
    }
    case 'road_status': {
      const routes = (d.routes as Json[]) ?? []
      if (!routes.length) return String(d.message ?? 'No routes')
      return routes.map((r) => `${r.id} ${r.status} ${r.travel_minutes} min`).join(', ')
    }
    case 'list_teams': {
      const teams = (d.teams as Json[]) ?? []
      return teams.length ? teams.map((t) => t.id).join(', ') : 'No matching team'
    }
    case 'search_guidelines': {
      const results = (d.results as Json[]) ?? []
      return results.length ? results.map((r) => r.citation).join(', ') : 'No relevant guideline'
    }
    case 'recall_facts': {
      const facts = (d.facts as Json[]) ?? []
      return facts.length ? `${facts.length} remembered fact(s)` : 'Nothing remembered'
    }
    case 'remember_fact':
      return 'Saved'
    case 'create_dispatch_task': {
      const task = d.task as Json | undefined
      return task ? `${task.id} dispatched` : 'Done'
    }
    default:
      return 'Done'
  }
}
