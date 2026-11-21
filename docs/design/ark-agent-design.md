# Ark-Agent — Design Document

**Case Study 90 · Driftwood Bay Flood Relief Coordination Centre**
*A ReAct planning agent (LangGraph) with memory, human approval, RAG and a React dashboard*

Status: **Approved** · Date: 2026-11-21

---

## 1. Intent

During monsoon floods, coordinators must match requests ("Ward 7 needs drinking water for 300 people by
evening") against depot stock, road conditions and volunteer teams — across long shifts and handovers.
Ark-Agent is an assistant that **reasons → acts (tool call) → observes** until it can propose a valid
relief plan, **remembers** what was decided (within a conversation and across shifts), and **never
dispatches a team without coordinator approval**.

It is a graded college project, so beyond working software it must show: clean modular structure,
strong typed schemas, tests, documentation, an evaluation report, and a readable git history.

## 2. Goals / Non-goals / Anti-goals

**Goals (map 1:1 to the PDF tasks)**

| # | PDF task | How Ark-Agent satisfies it |
|---|----------|----------------------------|
| T1 | Mock tools over JSON/SQLite: 3 depots, 6 routes, teams, task creator | Seed JSON → validated Pydantic models → PostgreSQL tables (SQLAlchemy + Alembic); 4 domain tools |
| T2 | LangGraph graph: reason / tool / finalise nodes, conditional loop edges, diagram | `StateGraph` with 5 nodes, 4 conditional routes, auto-exported Mermaid diagram + edge table in docs |
| T3 | Short-term memory (checkpointer) + long-term store persisting across restart | `PostgresSaver` per thread; `PostgresStore` for long-term facts; restart demo script |
| T4 | Human-in-the-loop interrupt before dispatch; pause & resume on approve/reject | `interrupt()` in an `approval` node; resume with `Command(resume=...)`; UI approval card |
| T5 | ≥6 scenarios incl. blocked road, insufficient stock, step limit; full traces | 8 scripted scenarios, traces saved as JSON + Markdown |
| T6 | Evaluate plan validity, steps, unnecessary tool calls; discuss a failure | Deterministic plan validator + metrics runner + evaluation report |
| + | RAG (extension) | Relief SOP knowledge base searched via a `search_guidelines` tool with citations |
| + | Dashboard (extension) | React + TypeScript dashboard: chat, live ReAct trace, approval, ops board, memory viewer |

**Non-goals:** real GIS/routing, real authentication, multi-user concurrency, cloud deployment.

**Anti-goals (would be a failure even if it "works")**
- A plan that uses a blocked road or allocates more stock than a depot holds.
- A dispatch task created without an explicit approval.
- An agent that silently loops past the step limit.
- Guidelines cited that were never retrieved.
- Messy history: one giant commit, or code dumped in a few huge files.

## 3. Constraints

- **LLM:** Groq (`GROQ_API_KEY` in `.env`). Default model `llama-3.3-70b-versatile` (strong tool calling),
  configurable.
- **Infrastructure:** Docker Compose with **one PostgreSQL 16 + pgvector** container holding ops data, RAG
  vectors, the LangGraph checkpointer and the long-term store. No separate vector server. In-memory
  implementations exist behind the same interfaces and are used only by the offline test suite.
- **Python env:** `uv` (creates `.venv`, lockfile `uv.lock`). Python 3.12.
- **Strong schemas:** Pydantic v2 everywhere (domain, tool inputs/outputs, agent plan, API DTOs) with
  enums, constrained fields and validators.
- **Git:** conventional commits, one logical step per commit, **no co-author / AI attribution lines**.
- **Structured build:** phase by phase (Section 9); each phase finishes with tests + docs + a commit before
  the next starts.

## 4. Approaches considered

| Approach | Trade-off | Verdict |
|----------|-----------|---------|
| **A. Prebuilt `create_react_agent`** | Few lines of code, but hides the graph; the PDF explicitly asks for our own reasoning / tool / finalise nodes, conditional edges and an explained diagram | Rejected — loses marks on T2 |
| **B. Custom `StateGraph` ReAct loop** (chosen) | More code, but every node, edge and stop condition is explicit, testable and documentable | **Chosen** |
| C. Plan-and-execute (planner + executor subgraphs) | More sophisticated, but it is not the ReAct pattern the case study names | Rejected |

| RAG store | Trade-off | Verdict |
|-----------|-----------|---------|
| Separate vector server (Qdrant / Chroma) next to Postgres | Two stateful services to run and keep in sync; redundant | Rejected |
| Pure in-memory everything | Simplest, but memory cannot survive a restart without file hacks | Rejected (kept only for tests) |
| **Postgres + pgvector for everything, local embeddings (fastembed `BAAI/bge-small-en-v1.5`, 384-d, CPU)** | One server; real persistence; SQL filters + vector search together; model download cached in a volume | **Chosen** |

## 5. Architecture

```
┌──────────────────────── React dashboard (Vite + TS) ────────────────────────┐
│ Chat │ Live ReAct trace │ Approval card │ Ops board (depots/roads/teams) │ Memory │
└───────────────────────────────┬─────────────────────────────────────────────┘
                                │ REST + Server-Sent Events
┌───────────────────────────────▼──────────── FastAPI ────────────────────────┐
│ /threads  /threads/{id}/messages (SSE)  /threads/{id}/resume  /ops/*  /memory │
└───────────────────────────────┬─────────────────────────────────────────────┘
                                │
┌───────────────────────────────▼──────── LangGraph agent ─────────────────────┐
│ load_memory → reason ⇄ tools → (approval ⏸) → finalize_plan → save_memory     │
│ Short-term: PostgresSaver (thread_id)   Long-term: PostgresStore              │
└──────┬──────────────────────┬───────────────────────────┬────────────────────┘
       │                      │                           │
┌──────▼───────┐   ┌──────────▼─────────┐     ┌───────────▼──────────┐
│ OpsRepository │   │ RAG: SOP markdown  │     │ Groq chat model      │
│ (SQLAlchemy)  │   │ → chunks → embed → │     │ (tool calling)       │
└──────┬───────┘   │ pgvector table     │     └──────────────────────┘
       │           └──────────┬─────────┘
┌──────▼──────────────────────▼──────────────────────────────────────┐
│ PostgreSQL 16 + pgvector  (Docker volume)                            │
│ depots · stock · routes · teams · wards · dispatch_tasks ·          │
│ guideline_chunks(vector 384) · checkpoints · store                  │
└──────────────────────────────────────────────────────────────────────┘
```

## 6. Detailed design

### 6.1 Folder structure (as built)

```
Ark-Agent/
├── README.md  PS.pdf  docker-compose.yml  .env.example  .gitignore
├── backend/                       # uv project (pyproject.toml, uv.lock), Dockerfile
│   ├── alembic.ini  migrations/   # Alembic: enums, tables, pgvector extension + HNSW index
│   ├── app/
│   │   ├── core/config.py         # pydantic-settings
│   │   ├── domain/                # base, enums, ward, depot, route, team, request, plan, task,
│   │   │                          # memory, results — pure Pydantic, no I/O
│   │   ├── db/                    # base, models (ORM), session, seeder, seed/*.json + loader
│   │   ├── repositories/          # interfaces (Protocol), rules, sql_ops, memory_ops, errors
│   │   ├── knowledge/             # 9 relief SOP markdown files (RAG corpus)
│   │   ├── rag/                   # types, chunker, embeddings, index, memory_index,
│   │   │                          # pgvector_index, ingest, retriever
│   │   ├── memory/                # factory (Postgres/in-memory saver + store), facts service
│   │   ├── tools/                 # schemas, ops_tools, guidelines, memory_tools, dispatch,
│   │   │                          # executor (safe run_tool), registry, context
│   │   ├── agent/                 # state, prompts, llm, policy, validator, nodes, routing,
│   │   │                          # graph, diagram
│   │   ├── api/                   # main (factory), container (wiring), deps, schemas,
│   │   │                          # streaming (SSE), routers/{threads,ops,memory,system}
│   │   └── evaluation/            # scenarios, runner, metrics, report
│   ├── scripts/                   # run_eval, demo_approval, demo_memory_persistence, export_graph
│   └── tests/                     # unit/ (offline), integration/ (Postgres), contract/, fakes
├── frontend/                      # Vite + React 19 + TypeScript + Tailwind; Dockerfile + nginx.conf
│   └── src/ api/  components/(ops/)  hooks/  lib/  types/
└── docs/                          # design/, architecture, database, graph, memory, rag,
                                   # tools-and-schemas, api, setup, evaluation, traces/
```

See [`docs/architecture.md`](../architecture.md) for the layering and request lifecycle.

### 6.2 Domain schemas (Pydantic v2, `extra="forbid"`, frozen where immutable)

**Enums:** `ResourceType` (drinking_water, food_ration, medicine_kit, boat, shelter_kit, blanket),
`Unit` (litre, packet, kit, unit), `RouteStatus` (open, slow, blocked), `TeamSkill` (logistics, medical,
boat_rescue, shelter), `TeamStatus` (available, deployed, resting), `TaskStatus` (pending_approval,
approved, rejected, dispatched), `Priority` (critical, high, medium, low).

| Model | Key fields & rules |
|-------|--------------------|
| `StockItem` | `resource: ResourceType`, `quantity: NonNegativeInt`, `unit: Unit`, `reserved: NonNegativeInt`; validator `reserved ≤ quantity`; computed `available` |
| `Depot` | `id` (pattern `^DEP-[A-C]$`), `name`, `location_zone`, `stock: dict[ResourceType, StockItem]` |
| `Route` | `id` (`^RT-\d{2}$`), `from_depot`, `to_ward`, `status`, `travel_minutes: PositiveInt`, `max_vehicle` (truck / boat / foot), `note` |
| `Team` | `id`, `name`, `skills: set[TeamSkill]`, `size: PositiveInt`, `status`, `base_depot`, `available_from: datetime` |
| `ReliefRequest` | `ward: str` (`^Ward \d+$`), `resource`, `people: PositiveInt`, `deadline: datetime\|None`, `priority` |
| `Allocation` | `depot_id`, `resource`, `quantity: PositiveInt` |
| `ReliefPlan` | `request`, `allocations: list[Allocation]` (min 1), `route_id`, `team_id`, `eta_minutes`, `meets_deadline: bool`, `rationale`, `citations: list[str]`, `shortfall: int` (≥0) |
| `DispatchTask` | `id` (UUID), `plan`, `status`, `created_at`, `decided_by`, `decision_note` |
| `MemoryFact` | `key`, `kind` (decision / reservation / road_report / note), `content`, `ward`, `created_at`, `source_thread` |

Every tool has a Pydantic `args_schema`, so malformed LLM arguments are rejected and returned to the model as
structured errors it can recover from. All tools return typed `ToolResult` JSON
(`ok`, `data`, `error`), never free text.

### 6.3 Mock data (seed)

- **3 depots** (A: north / high ground, B: central, C: coastal), each with deliberately uneven stock.
- **6 routes:** includes one blocked route (RT-03), one slow route, and a boat-only route to a flooded ward.
- **~8 volunteer teams** with mixed skills and statuses.
- **Wards 1–12** with population hints.

The seed is designed so the required scenarios actually happen: Ward 7's preferred road is blocked, and
medicine kits are short at every depot. Data lives in Postgres (schema via Alembic, seeded idempotently on
startup), and `POST /api/ops/reset` restores the seed.

**Database tables:** `wards`, `depots`, `stock_items` (unique depot+resource, CHECK reserved ≤ quantity),
`routes` (FK depot, FK ward), `teams`, `team_skills`, `dispatch_tasks` (plan JSONB, status enum),
`stock_reservations` (FK task), `guideline_chunks` (embedding `vector(384)`, HNSW index). LangGraph's
`PostgresSaver` / `PostgresStore` create their own tables. Stock reservation runs in a single transaction
with row locks so stock can never go negative. Documented in `docs/database.md` with an ER diagram.

### 6.4 Tools

| Tool | Side effect | Notes |
|------|-------------|-------|
| `stock_lookup(resource, depot_id?)` | none | All depots if `depot_id` omitted; returns available = quantity − reserved |
| `road_status(ward?, route_id?)` | none | Routes to a ward with status + travel time |
| `list_teams(skill?, status?)` | none | Filterable |
| `search_guidelines(query, k=3)` | none | RAG; returns chunks with `source#section` citation ids |
| `recall_facts(ward?, query?)` | none | Reads long-term memory |
| `remember_fact(kind, content, ward?)` | writes memory | Agent records decisions / road reports |
| `create_dispatch_task(plan)` | **reserves stock + creates task** | **Never executed by the tool node.** The `approval` node pauses with the proposed plan (no DB write before the pause); on approve it creates the task and reserves stock in one transaction; on reject it records a rejected task without reserving stock |

### 6.5 Agent graph (custom StateGraph)

**State (`AgentState`, TypedDict):** `messages` (add_messages reducer), `request: ReliefRequest|None`,
`step_count`, `max_steps`, `tool_calls_log`, `proposed_plan: ReliefPlan|None`, `approval: Literal[...]|None`,
`status: Literal["running","awaiting_approval","completed","rejected","step_limit","needs_input"]`.

**Nodes**
1. `load_memory`: pulls relevant long-term facts for the ward(s) into a system note.
2. `reason`: Groq LLM bound to tools; increments `step_count`.
3. `tools`: executes read-only and memory tools; logs each call.
4. `approval`: `interrupt()` with the proposed dispatch; resumes with approve / reject (+note).
5. `finalize_plan`: validates the plan with `validator.py`, writes the decision to long-term memory, and
   produces the final structured answer. A blocked or impossible plan returns the shortfall and alternatives
   instead of pretending.

**Conditional edges (from `reason`)**
- has read-only tool calls → `tools` → back to `reason`
- calls `create_dispatch_task` → `approval`
- no tool calls (plan ready / needs info) → `finalize_plan`
- `step_count ≥ max_steps` (default 8) → `finalize_plan` with `status="step_limit"`

From `approval`: approved → create task + reserve stock → `finalize_plan`; rejected → back to `reason` with the
coordinator's note so it can re-plan. Every tool call in the turn gets a matching `ToolMessage` (read-only calls
are executed; the dispatch call receives the approval outcome), so the message history stays valid for the LLM.

Diagram: exported via `graph.get_graph().draw_mermaid()` into `docs/graph.md`, with an edge-by-edge
explanation table.

### 6.6 Memory

- **Short-term:** `PostgresSaver` checkpointer keyed by `thread_id` (one thread = one coordinator
  conversation). "What about Ward 9 instead?" resolves the resource and quantity from earlier turns.
  Conversations also survive a backend restart.
- **Long-term:** LangGraph `PostgresStore`, namespaced `("ops", "facts")` and `("ops", "decisions")`, values
  validated by the `MemoryFact` schema.
- **Persistence demo (PDF T3):** `scripts/demo_memory_persistence.py` runs shift 1 in one process, exits,
  starts a fresh process (shift 2, new thread) and shows the agent recalling
  "Depot B reserved 200 L for Ward 7".
- Tests swap in `InMemorySaver` / `InMemoryStore` through the same factory.

### 6.7 RAG

- **Corpus:** 8–10 representative SOP markdown files (water per person per day, medicine prioritisation, boat
  safety thresholds, shelter standards, vulnerable groups, dispatch protocol, road-closure protocol, handover
  checklist). Each file has front-matter (`title`, `source`, `version`).
- **Pipeline:** heading-aware chunking (~400 tokens, 60 overlap) → fastembed embeddings → `guideline_chunks`
  pgvector table. Ingestion is idempotent: deterministic chunk ids from a content hash, so re-running
  updates instead of duplicating.
- **Retrieval:** top-k=3 with a score threshold, citations returned as `sop-water.md#daily-allowance`. The
  validator checks that every citation in a plan was actually retrieved in that run.

### 6.8 API (FastAPI)

| Method & path | Purpose |
|---------------|---------|
| `POST /api/threads` | Create a conversation thread |
| `POST /api/threads/{id}/messages` | Send a message; **SSE stream** of events: `thought`, `tool_call`, `tool_result`, `interrupt`, `plan`, `done`, `error` |
| `POST /api/threads/{id}/resume` | `{decision: "approve"\|"reject", note?}` |
| `GET /api/threads/{id}/state` | Current state / history |
| `GET /api/ops/depots` · `/routes` · `/teams` · `/tasks` · `POST /api/ops/reset` | Ops board |
| `PATCH /api/ops/routes/{id}` | Toggle road status (for live demos) |
| `GET /api/memory` · `DELETE /api/memory` | Long-term memory viewer |
| `GET /api/graph` | Mermaid source of the graph |

### 6.9 Dashboard (React + TS + Tailwind, Vite)

```
┌ Ark-Agent · Driftwood Bay Relief ──────────────────────── [Reset data] ┐
│ ┌ Chat ─────────────────┐ ┌ ReAct trace (live) ─────────────────────┐ │
│ │ You: Ward 7 needs ... │ │ 1 Thought: need water stock            │ │
│ │ Agent: Plan ...       │ │   → stock_lookup(water) ✓ 3 depots      │ │
│ │ ┌ Approval needed ──┐ │ │ 2 Thought: check roads to Ward 7       │ │
│ │ │ Dispatch T-3 ...  │ │ │   → road_status(Ward 7) ✓ RT-03 blocked │ │
│ │ │ [Approve][Reject] │ │ │ step 4/8                                │ │
│ └─────────────────────┘ └────────────────────────────────────────┘ │
│ ┌ Depots ──┐ ┌ Roads ───────┐ ┌ Teams ──┐ ┌ Long-term memory ─────┐ │
│ └──────────┘ └──────────────┘ └─────────┘ └───────────────────────┘ │
│ [Graph] tab: rendered Mermaid diagram                                │
└──────────────────────────────────────────────────────────────────────┘
```

API types are mirrored in `frontend/src/types/` (hand-written to match the Pydantic DTOs).

### 6.10 Evaluation

**Scenarios (8):**
1. Normal: water for Ward 7
2. Preferred road blocked
3. Insufficient stock at every depot
4. Step-limit hit (max_steps forced to 3)
5. Follow-up "what about Ward 9 instead?"
6. Coordinator rejects, then the agent re-plans
7. Cross-shift memory recall after restart
8. Guideline-dependent request (RAG)

**Metrics:**
- plan validity: the deterministic validator checks stock ≤ available, route not blocked, team skill match
  and citations retrieved
- steps taken
- unnecessary tool calls: duplicate identical calls, plus calls irrelevant to the resource
- approval respected (0 dispatches without approval)
- latency and tokens

**Outputs:** `docs/traces/*.json|md` and `docs/evaluation.md`, which includes a summary table and a written
failure analysis with a mitigation.

### 6.11 Testing

pytest. The **unit suite is fully offline** (no Docker, no Groq):
- schema validation
- repository and tools
- validator
- chunker and retriever (with BM25 fallback)
- memory snapshot/restore
- graph routing using a scripted fake chat model (step limit, interrupt / resume, rejection path)

An **integration suite** (`pytest -m integration`) runs against the Compose Postgres: migrations,
repository, pgvector retrieval, checkpointer and store persistence. Groq is only used in the evaluation
runner and the demos.

## 7. Error handling

- Tool errors come back as structured `ToolResult(ok=False, error=...)` so the agent can recover.
- Groq rate limits and transient errors are handled with retry + backoff and surfaced as SSE `error` events.
- Missing `GROQ_API_KEY` gives a clear startup message.

## 8. Git & documentation conventions

- Conventional commits describing the feature (`feat(tools): add stock lookup with depot filter`), never
  plan step / phase numbers, and no AI attribution lines.
- `docs/` is updated in the same phase as the code it describes, and the README has a PDF-task → file map.

## 9. Build phases (each ends: tests green → docs → commit)

| Phase | Deliverable |
|-------|-------------|
| 0 | Repo init, uv project, folder skeleton, tooling (ruff, pytest), README stub |
| 1 | Domain schemas + seed data |
| 1b | Docker Compose (pgvector), SQLAlchemy models, Alembic migration, seeder, SQL + in-memory repositories |
| 2 | Tools with arg schemas + registry (T1 tools) |
| 3 | RAG: corpus, chunker, embeddings, index, `search_guidelines` |
| 4 | Memory: checkpointer + long-term store with snapshot |
| 5 | Agent graph: state, prompts, nodes, routing, interrupt, validator, diagram (T2–T4) |
| 6 | FastAPI + SSE streaming |
| 7 | React dashboard |
| 8 | Scenarios, evaluation runner, traces, evaluation report (T5–T6) |
| 9 | Final docs, demo scripts, README polish |

## 10. Key design decisions

1. Default model `llama-3.3-70b-versatile` on Groq; switchable via `.env`.
2. One Postgres 16 + pgvector container for all state; no separate vector server.
3. SQLAlchemy 2.0 (sync, psycopg 3) + Alembic migrations; LangGraph `PostgresSaver` / `PostgresStore`.
4. Local fastembed embeddings (384-d) running inside the backend; model cached in a Docker volume.
5. The SOP knowledge base is representative but fictional, modelled on common humanitarian relief standards.
6. Tailwind for dashboard styling; no component library. Frontend served by nginx in Docker, which proxies `/api`.
7. Unit tests use in-memory implementations + a fake LLM, so they are free, offline and deterministic.
