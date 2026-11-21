# HTTP API

FastAPI service in `backend/app/api/`. Interactive OpenAPI docs: <http://localhost:8000/docs>.
All routes are under `/api`.

## Conversation threads

| Method | Path | Body | Response |
|--------|------|------|----------|
| `POST` | `/threads` | | `201 {"thread_id": "…"}` |
| `POST` | `/threads/{id}/messages` | `{"content": str (1-2000), "max_steps"?: 1-25}` | **SSE stream** |
| `POST` | `/threads/{id}/resume` | `{"decision": "approve"\|"reject"\|"revise", "note"?: str}` | **SSE stream** |
| `GET` | `/threads/{id}` | | `ThreadState`: messages, status, step count, pending approval |

- `409` when a message is sent while a dispatch awaits approval, when resuming a thread with
  nothing pending, or when a run is already in progress on that thread.
- `422` for schema violations (empty content, unknown decision, `revise` without a note…).

### Server-Sent Events

Each frame is `event: <type>` + `data: {"type", "step", "data"}`:

| Type | `data` | Emitted when |
|------|--------|--------------|
| `run_started` | `thread_id` | Stream opened |
| `thought` | `text` | The model wrote reasoning alongside tool calls |
| `tool_call` | `id`, `name`, `args` | The model acts |
| `tool_result` | `tool_call_id`, `name`, `ok`, `data` \| `error` | Observation (including validation feedback and approval outcomes) |
| `interrupt` | `id`, `type: dispatch_approval`, `plan`, `message` | Paused for the coordinator |
| `answer` | `text` | Final reply for this request |
| `done` | `status` (`answered`, `dispatched`, `rejected`, `step_limit`, `awaiting_approval`), `step_count` | Run finished or paused |
| `error` | `message` | LLM or server failure, or a missing `GROQ_API_KEY` |

Example:

```text
event: tool_call
data: {"type":"tool_call","step":2,"data":{"id":"call_2","name":"road_status","args":{"ward_id":"W-07"}}}

event: interrupt
data: {"type":"interrupt","step":3,"data":{"type":"dispatch_approval","plan":{"ward_id":"W-07",…}}}
```

## Operations

| Method | Path | Notes |
|--------|------|-------|
| `GET` | `/ops/wards` · `/ops/depots` · `/ops/teams` | Seeded reference data with live stock and status |
| `GET` | `/ops/routes?ward_id=W-07` | Optional ward filter |
| `PATCH` | `/ops/routes/{id}` | `{"status": "open"\|"slow"\|"blocked", "note"?}`. Simulates a road report |
| `GET` | `/ops/tasks` | Dispatch decisions, newest first |
| `POST` | `/ops/reset` | Restore seed data (tasks cleared; memory and RAG index kept) |

## Memory, knowledge and system

| Method | Path | Notes |
|--------|------|-------|
| `GET` | `/memory?ward_id=&kind=&limit=` | Long-term facts, newest first |
| `DELETE` | `/memory` | Clear long-term facts |
| `GET` | `/knowledge/search?q=&k=` | Direct RAG search with citations and scores |
| `GET` | `/graph` | Mermaid source of the agent graph |
| `GET` | `/health` | `{"status", "database", "llm_configured", "model"}` |

## Startup sequence (`production_container`)

1. `alembic upgrade head`
2. Seed operational tables if empty
3. Sync the SOP knowledge base into pgvector (only new or changed chunks are embedded)
4. Open the Postgres checkpointer and store (`setup()` creates LangGraph tables)
5. Build the Groq chat model. If `GROQ_API_KEY` is missing the API still serves operations and
   reports the problem as an `error` event on agent endpoints.
