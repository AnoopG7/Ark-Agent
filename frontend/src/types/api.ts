// Mirrors the Pydantic schemas in backend/app/domain and backend/app/api/schemas.py.

export type ResourceType =
  | 'drinking_water'
  | 'food_ration'
  | 'medicine_kit'
  | 'boat'
  | 'shelter_kit'
  | 'blanket'
export type Unit = 'litre' | 'packet' | 'kit' | 'unit' | 'piece'
export type RouteStatus = 'open' | 'slow' | 'blocked'
export type VehicleType = 'truck' | 'boat' | 'foot'
export type TeamSkill = 'logistics' | 'medical' | 'boat_rescue' | 'shelter'
export type TeamStatus = 'available' | 'deployed' | 'resting'
export type TaskStatus = 'dispatched' | 'rejected'
export type FactKind = 'decision' | 'reservation' | 'road_report' | 'rejection' | 'note'

export interface Ward {
  id: string
  name: string
  population: number
  zone: string
}

export interface StockItem {
  resource: ResourceType
  quantity: number
  reserved: number
  available: number
  unit: Unit
}

export interface Depot {
  id: string
  name: string
  zone: string
  stock: StockItem[]
}

export interface Route {
  id: string
  name: string
  depot_id: string
  ward_id: string
  status: RouteStatus
  travel_minutes: number
  vehicle: VehicleType
  note: string
}

export interface Team {
  id: string
  name: string
  skills: TeamSkill[]
  size: number
  status: TeamStatus
  base_depot: string
  vehicle: VehicleType
}

export interface Allocation {
  depot_id: string
  resource: ResourceType
  quantity: number
  route_id: string
}

export interface ReliefPlan {
  ward_id: string
  resource: ResourceType
  people: number
  quantity_required: number
  allocations: Allocation[]
  team_id: string
  eta_minutes: number
  rationale: string
  citations: string[]
  total_allocated: number
  shortfall: number
}

export interface DispatchTask {
  id: string
  plan: ReliefPlan
  status: TaskStatus
  created_at: string
  decision_note: string
  thread_id: string | null
}

export interface MemoryFact {
  id: string
  kind: FactKind
  content: string
  ward_id: string | null
  created_at: string
  source_thread: string | null
}

export interface Health {
  status: 'ok' | 'degraded'
  database: boolean
  llm_configured: boolean
  model: string
}

export type RunStatus =
  | 'new'
  | 'running'
  | 'answered'
  | 'dispatched'
  | 'rejected'
  | 'step_limit'
  | 'awaiting_approval'

export interface ToolCall {
  id: string
  name: string
  args: Record<string, unknown>
}

export interface ChatMessage {
  role: 'user' | 'assistant' | 'tool'
  content: string
  tool_calls: ToolCall[]
  name: string | null
  tool_call_id: string | null
  ok: boolean | null
}

export interface PendingApproval {
  id: string
  type: 'dispatch_approval'
  plan: ReliefPlan
  message: string
}

export interface ThreadState {
  thread_id: string
  status: RunStatus
  step_count: number
  messages: ChatMessage[]
  pending_approval: PendingApproval | null
}

export type Decision = 'approve' | 'reject' | 'revise'

export type AgentEvent =
  | { type: 'run_started'; step: number; data: { thread_id: string } }
  | { type: 'thought'; step: number; data: { text: string } }
  | { type: 'tool_call'; step: number; data: ToolCall }
  | {
      type: 'tool_result'
      step: number
      data: { tool_call_id: string; name: string; ok: boolean; data?: unknown; error?: string | null }
    }
  | { type: 'interrupt'; step: number; data: PendingApproval }
  | { type: 'answer'; step: number; data: { text: string } }
  | { type: 'done'; step: number; data: { status: RunStatus; step_count: number } }
  | { type: 'error'; step: number; data: { message: string } }
