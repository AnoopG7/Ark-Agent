# Tools and Schemas

## Domain schemas (`backend/app/domain`)

All models extend `DomainModel` (`extra="forbid"`, whitespace trimmed, `validate_assignment`).
Computed fields are serialised and ignored on input, so every model round-trips through JSON.

| Model | Fields | Rules |
|-------|--------|-------|
| `Ward` | `id` `^W-\d{2}$`, `name`, `population > 0`, `zone` | |
| `StockItem` | `resource`, `quantity ≥ 0`, `reserved ≥ 0`, `unit`; computed `available` | `reserved ≤ quantity`; unit must match the resource (`drinking_water` → litre…) |
| `Depot` | `id` `^DEP-[A-C]$`, `name`, `zone`, `stock[]` | one stock item per resource |
| `Route` | `id` `^RT-\d{2}$`, `depot_id`, `ward_id`, `status` (open/slow/blocked), `travel_minutes` 1-1440, `vehicle` (truck/boat/foot), `note` | |
| `Team` | `id` `^TM-\d{2}$`, `skills[]` (≥1), `size` 1-50, `status`, `base_depot`, `vehicle` | |
| `ReliefRequest` | `ward_id`, `resource`, `people` 1-100000, `quantity_needed?`, `deadline_hours?` (0-72], `priority` | |
| `Allocation` | `depot_id`, `resource`, `quantity > 0`, `route_id` | |
| `ReliefPlan` | `ward_id`, `resource`, `people`, `quantity_required`, `allocations` (1-3), `team_id`, `eta_minutes`, `rationale`, `citations` (`file.md#section`); computed `total_allocated`, `shortfall` | allocations match the plan resource; at most one per depot |
| `DispatchTask` | `id` `^TASK-\d{4,}$`, `plan`, `status` (dispatched/rejected), `created_at` (tz-aware), `decision_note`, `thread_id` | |
| `MemoryFact` | `id`, `kind` (decision/reservation/road_report/rejection/note), `content` 1-500, `ward_id?`, `created_at`, `source_thread?` | |
| `ToolResult` | `ok`, `data`, `error` | `ok` XOR `error` |

## Agent tools (`backend/app/tools`)

Every tool has a Pydantic `args_schema`, which is what the LLM sees as JSON schema. Tools run
through `run_tool`, which converts schema errors, repository errors and unexpected exceptions
into `ToolResult(ok=False, error=...)`. The agent reads the error and recovers instead of the
run crashing.

| Tool | Arguments | Returns | Side effects |
|------|-----------|---------|--------------|
| `stock_lookup` | `resource`, `depot_id?` | per-depot quantity / reserved / available, total available | none |
| `road_status` | `ward_id?`, `route_id?` | routes sorted by travel time with `usable` flag; message if no route reaches the ward | none |
| `list_teams` | `skill?`, `status?` (default available) | teams with skills, vehicle, base | none |
| `search_guidelines` | `query` (3-300 chars), `k` 1-5 | passages with `citation`, `title`, `text`, `score` (≥ 0.60) | none |
| `recall_facts` | `ward_id?`, `kind?` | up to 10 remembered facts, newest first | none |
| `remember_fact` | `kind`, `content` (5-500), `ward_id?` | the saved fact (with `source_thread`) | writes long-term memory |
| `create_dispatch_task` | a full `ReliefPlan` | the dispatched task, or why not | **never executed by the tools node**: routed to the approval checkpoint; on approval reserves stock and deploys the team |

`APPROVAL_REQUIRED = {"create_dispatch_task"}` in `tools/registry.py` is the single list the
router consults. Adding another side-effecting tool to it automatically puts it behind the
human checkpoint.

## Error handling summary

| Situation | What happens |
|-----------|--------------|
| LLM sends malformed tool arguments | `ToolResult` error with field-level messages; the model retries with corrected arguments |
| Unknown ward / depot / route / team | `NotFoundError` → `ToolResult` error |
| Plan uses a blocked road, phantom stock, wrong team | stopped by the validator before the coordinator sees it; violations returned to the model |
| Stock taken between proposal and approval | dispatch transaction fails cleanly; the model is told and re-plans |
| Groq `tool_use_failed` / rate limit | retried with exponential backoff (5 attempts) |
| Groq down / key missing | SSE `error` event; the operations API keeps working |
| Step budget exhausted | pending calls answered "not executed", coordinator told nothing was dispatched |
