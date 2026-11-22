# Ark-Agent Implementation Plan

**Goal:** Build the Driftwood Bay flood-relief ReAct agent (LangGraph + Groq) with Postgres/pgvector persistence, RAG over relief SOPs, human approval before dispatch, a FastAPI SSE backend, a React dashboard, scenario evaluation and docs.

**Architecture:** A custom LangGraph `StateGraph` (load_memory → reason ⇄ tools → approval interrupt → finalize_plan) calls typed tools. The tools sit on repository interfaces with Postgres implementations (used by the app) and in-memory implementations (used by unit tests). FastAPI streams graph events over SSE to a Vite/React dashboard. Docker Compose runs `db` (pgvector), `backend` and `frontend`.

**Tech Stack:** Python 3.12, uv, LangGraph, langchain-groq, langgraph-checkpoint-postgres, SQLAlchemy 2 (psycopg 3), Alembic, pgvector, fastembed, FastAPI, pytest, ruff; React 18 + TypeScript + Vite + Tailwind; Docker Compose.

**Design:** `docs/design/ark-agent-design.md`

## Global Constraints

- Python env via **uv** only (`backend/.venv`, `uv.lock` committed). Python 3.12.
- Backend package lives at `backend/app/` (imports `from app...`).
- LLM: Groq, default `openai/gpt-oss-120b`, read from `GROQ_MODEL`; key `GROQ_API_KEY`.
- One Postgres 16 + pgvector container; no other stateful services.
- Embeddings: fastembed `BAAI/bge-small-en-v1.5`, dimension **384**.
- Pydantic v2 models use `ConfigDict(extra="forbid")`. IDs: depots `^DEP-[A-C]$`, routes `^RT-\d{2}$`, teams `^TM-\d{2}$`, wards `^W-\d{2}$` (display name "Ward N").
- Agent `max_steps` default **8**. `create_dispatch_task` is never executed without an approval.
- Unit tests must be offline (no Docker, no Groq). Integration tests are marked `@pytest.mark.integration`.
- Commits: conventional, feature-described, **no phase/step wording, no co-author lines**.

## Risk-driven tests

1. **Approval bypass:** the LLM calls `create_dispatch_task` alongside other tools in one turn. Expected: the dispatch is still routed to approval and nothing is reserved before approval. Test: `test_dispatch_in_parallel_calls_still_interrupts` (graph task).
2. **Over-allocation race:** two approved dispatches request the last stock. Expected: the second fails cleanly, and stock is never negative. Test: `test_reserve_insufficient_raises_and_leaves_stock` (repositories task).
3. **Malformed tool args:** unknown resource, depot `DEP-Z`, negative people. Expected: `ToolResult(ok=False)` with a readable error, and the graph continues. Test: `test_tools_return_error_on_invalid_args` (tools task).
4. **Resume on a thread with no pending interrupt.** Expected: API returns 409, not 500. Test: `test_resume_without_interrupt_returns_409` (API task).
5. **Groq unavailable / missing key.** Expected: SSE `error` event with a clear message; the app still starts and the ops endpoints work. Test: `test_stream_emits_error_event_when_llm_fails` (API task).

---

### Task 1: Repository scaffold & tooling

**Files:** `.gitignore`, `.env.example`, `README.md`, `backend/pyproject.toml`, `backend/app/__init__.py` (+ subpackage `__init__`s), `backend/tests/conftest.py`, `backend/tests/unit/test_smoke.py`

- [ ] `git init`; `uv init --package`-style `pyproject.toml` with deps + dev deps (pytest, ruff); configure ruff (line 100) and pytest markers (`integration`).
- [ ] Smoke test `test_app_imports` asserts `import app` works → `uv run pytest` passes.
- [ ] Commit `chore: scaffold backend project with uv, ruff and pytest`. Commit the design docs separately: `docs: add design and implementation plan`.

### Task 2: Configuration

**Files:** `backend/app/core/config.py`, `backend/tests/unit/test_config.py`
**Produces:** `Settings` (pydantic-settings) with `database_url: str`, `groq_api_key: SecretStr | None`, `groq_model: str = "openai/gpt-oss-120b"`, `max_steps: int = 8` (ge=1, le=25), `rag_top_k: int = 3`, `rag_min_score: float = 0.35`, `embedding_model: str`, `cors_origins: list[str]`; `get_settings() -> Settings` (lru_cache).

- [ ] Tests: defaults; env override `MAX_STEPS=3`; `MAX_STEPS=0` raises `ValidationError`.
- [ ] Commit `feat(config): add typed settings loaded from environment`.

### Task 3: Domain schemas

**Files:** `backend/app/domain/{enums,ward,depot,route,team,request,plan,task,memory,results}.py`, `backend/tests/unit/test_domain.py`
**Produces:** enums `ResourceType, Unit, RouteStatus, VehicleType, TeamSkill, TeamStatus, TaskStatus, Priority, FactKind`; `RESOURCE_UNITS: dict[ResourceType, Unit]`; models `Ward, StockItem(available: computed), Depot, Route, Team, ReliefRequest, Allocation, ReliefPlan, DispatchTask, MemoryFact, ToolResult(ok, data, error)`.

- [ ] Tests: `StockItem(quantity=10, reserved=11)` raises; `available == quantity - reserved`; bad depot id raises; `ReliefPlan` with empty allocations raises; `extra` fields are rejected; an `Allocation` with a unit mismatched to the resource raises.
- [ ] Commit `feat(domain): add validated relief operation schemas`.

### Task 4: Seed data

**Files:** `backend/app/db/seed/{wards,depots,routes,teams}.json`, `backend/app/db/seed/loader.py`, `backend/tests/unit/test_seed.py`
**Produces:** `load_seed() -> SeedData` (Pydantic: `wards, depots, routes, teams`), with referential checks (route depots and wards exist; team base depots exist).

- [ ] Data: 12 wards; 3 depots; exactly 6 routes, of which RT-03 (DEP-B→W-07) is blocked, one is slow, and one is boat-only to W-09; 8 teams; medicine kits total < 150 across depots.
- [ ] Tests: counts (3 depots / 6 routes); referential integrity; at least one blocked route; a scenario guarantee that the medicine total is below 150.
- [ ] Commit `feat(data): add Driftwood Bay seed dataset`.

### Task 5: Repository interface + in-memory implementation

**Files:** `backend/app/repositories/{interfaces,errors,memory_ops}.py`, `backend/tests/unit/test_memory_repo.py`
**Produces:** `OpsRepository` Protocol with `dispatch(plan, note) -> DispatchTask` (create + reserve in one transaction; marks team deployed), `record_rejection(plan, note) -> DispatchTask`, `list_depots()`, `get_stock(resource, depot_id=None) -> list[tuple[Depot, StockItem]]`, `list_routes(ward_id=None, route_id=None)`, `update_route_status(route_id, status)`, `list_teams(skill=None, status=None)`, `list_tasks()`, `list_wards()`, `reset()`. Errors: `NotFoundError`, `InsufficientStockError`, `ConflictError`. `InMemoryOpsRepository(seed)` uses a lock.

- [ ] Tests: filters; `test_reserve_insufficient_raises_and_leaves_stock`; dispatching a deployed team raises `ConflictError`; reset restores the seed.
- [ ] Commit `feat(repositories): add ops repository interface with in-memory store`.

### Task 6: Postgres schema, migrations, SQL repository, Docker db

**Files:** `docker-compose.yml` (db service, `pgvector/pgvector:pg16`, healthcheck, volume), `backend/app/db/{base,session,models,seeder}.py`, `backend/alembic.ini`, `backend/migrations/{env.py,versions/0001_initial.py}`, `backend/app/repositories/sql_ops.py`, `backend/tests/integration/test_sql_repo.py`, `docs/database.md`
**Produces:** `SqlOpsRepository(session_factory)` that implements `OpsRepository`; `seed_database(session, seed, *, force=False)` (idempotent); migration creates `CREATE EXTENSION vector`, all tables, CHECK `reserved <= quantity`, and `guideline_chunks(embedding vector(384))` with an HNSW cosine index.

- [ ] Integration tests reuse the in-memory repo's behavioural tests through a shared parametrised contract fixture (`tests/contract/ops_repo_contract.py`), so both implementations are held to the same contract.
- [ ] `dispatch` uses `SELECT ... FOR UPDATE` on stock rows.
- [ ] `docker compose up -d db && uv run alembic upgrade head && uv run pytest -m integration` passes.
- [ ] Commit `feat(db): add Postgres schema, migrations and SQL ops repository`.

### Task 7: Tools

**Files:** `backend/app/tools/{context,stock,roads,teams,dispatch,memory_tools,registry}.py`, `backend/tests/unit/test_tools.py`
**Produces:** `ToolContext(repo, store, retriever)` provided through a context var / `RunnableConfig["configurable"]`; LangChain `@tool` functions with Pydantic `args_schema`: `stock_lookup`, `road_status`, `list_teams`, `create_dispatch_task`, `remember_fact`, `recall_facts`. All return `ToolResult.model_dump()` JSON. `registry.ALL_TOOLS`, `registry.APPROVAL_REQUIRED = {"create_dispatch_task"}`. `create_dispatch_task` is declared to the LLM but is never executed by the tool node; the `approval` node handles it (see Task 10).

- [ ] Tests: each tool's happy path; `test_tools_return_error_on_invalid_args`; `road_status("W-07")` shows RT-03 blocked.
- [ ] Commit `feat(tools): add stock, road, team, dispatch and memory tools`.

### Task 8: RAG

**Files:** `backend/app/knowledge/*.md` (8 SOPs), `backend/app/rag/{chunker,embeddings,index,memory_index,pgvector_index,ingest,retriever}.py`, `backend/app/tools/guidelines.py`, tests `unit/test_chunker.py`, `unit/test_retriever.py`, `integration/test_pgvector_index.py`, `docs/rag.md`
**Produces:** `chunk_markdown(text, source, max_chars=1600, overlap=240) -> list[Chunk]` (heading-aware; `Chunk(id=sha1(source+section+text)[:16], source, section, text)`); `Embedder` Protocol (`embed_documents`, `embed_query`, `dim`) with `FastEmbedEmbedder` and `HashEmbedder` (tests); `VectorIndex` Protocol (`upsert(chunks, vectors)`, `search(vec, k) -> list[ScoredChunk]`) with in-memory and pgvector implementations; `ingest_knowledge(dir, embedder, index) -> int`; `Retriever.search(query, k, min_score)`; `search_guidelines` tool returns citations `source#section`.

- [ ] Tests: chunks never split a heading section unless it is too long; ingesting twice gives the same count (idempotent); a query about "drinking water per person" retrieves `sop-water-supply.md` with the HashEmbedder.
- [ ] Commit `feat(rag): add relief SOP knowledge base with pgvector retrieval`.

### Task 9: Memory

**Files:** `backend/app/memory/{factory,facts}.py`, `backend/tests/unit/test_facts.py`, `backend/tests/integration/test_memory_persistence.py`, `docs/memory.md`
**Produces:** `build_checkpointer(settings, *, in_memory=False)` context manager; `build_store(settings, *, in_memory=False)` context manager; `FactsService(store)` with `save(fact: MemoryFact)`, `list(ward_id=None, limit=20) -> list[MemoryFact]`, namespace `("ops","facts")`.

- [ ] Integration test: write a fact, close the store, reopen a new store, and the fact is present.
- [ ] Commit `feat(memory): add Postgres checkpointer and long-term facts store`.

### Task 10: Agent graph

**Files:** `backend/app/agent/{state,prompts,llm,nodes,routing,graph,validator}.py`, `backend/tests/unit/{test_validator,test_graph}.py`, `backend/tests/fakes.py`, `backend/scripts/export_graph.py`, `docs/graph.md`
**Produces:** `AgentState`; `build_graph(*, llm, tools_ctx, checkpointer, store, max_steps) -> CompiledStateGraph`; nodes `load_memory`, `reason`, `tools`, `approval` (calls `interrupt({...proposed plan...})` **before any write**, expects resume `{"decision": "approve"|"reject", "note": str}`), `finalize_plan`; `route_after_reason(state) -> Literal["tools","approval","finalize_plan"]`; `validate_plan(plan, repo, retrieved_citations) -> list[str]` (violations). `FakeToolCallingModel(responses: list[AIMessage])` in tests.

- [ ] Tests (fake LLM, in-memory everything): read-only tool loop; `test_step_limit_routes_to_finalize`; `test_dispatch_requires_interrupt`; `test_dispatch_in_parallel_calls_still_interrupts` (also asserts every tool_call_id has a ToolMessage after approve and after reject); approve → task approved + stock reserved; reject → status rejected and no reservation; follow-up on the same thread sees earlier messages; validator flags a blocked route, over-allocation and an unretrieved citation.
- [ ] `export_graph.py` writes the Mermaid diagram to `docs/graph.md`; the doc explains every edge.
- [ ] Commit `feat(agent): add ReAct planning graph with approval interrupt and step limit`.

### Task 11: API

**Files:** `backend/app/api/{main,deps,schemas,streaming}.py`, `backend/app/api/routers/{threads,ops,memory,graph}.py`, `backend/tests/unit/test_api.py`, `docs/api.md`
**Produces:** endpoints per spec §6.8. SSE event types: `thought, tool_call, tool_result, interrupt, plan, done, error`, each `{type, data, step}`. App lifespan wires Postgres, migrations check, seed, and ingestion. `create_app(container: AppContainer | None = None)` so tests inject in-memory deps + the fake LLM.

- [ ] Tests: `test_resume_without_interrupt_returns_409`; `test_stream_emits_error_event_when_llm_fails`; the stream produces an `interrupt` event for a dispatch; ops endpoints return the seed; `PATCH /api/ops/routes/RT-01` toggles status.
- [ ] Commit `feat(api): add FastAPI service with streaming agent endpoints`.

### Task 12: Backend container + full Compose

**Files:** `backend/Dockerfile`, `backend/docker-entrypoint.sh` (alembic upgrade + uvicorn), `docker-compose.yml` (backend service, fastembed cache volume), `docs/setup.md`
- [ ] `docker compose up --build backend db`; `curl localhost:8000/api/health` returns `{"status":"ok","db":"ok"}`.
- [ ] Commit `build: containerise backend with uv and wire into compose`.

### Task 13: Frontend

**Files:** `frontend/` (Vite React TS), `src/types/api.ts`, `src/api/client.ts` (fetch + SSE parser over `fetch` streaming), `src/hooks/useAgentThread.ts`, components `ChatPanel, TracePanel, ApprovalCard, DepotsCard, RoutesCard, TeamsCard, MemoryPanel, GraphView, Header`, `frontend/Dockerfile` + `nginx.conf` (proxy `/api`).
- [ ] `npm run build` and `npm run lint` pass; manual check against the running backend: send a request → trace streams → approval card → approve → ops board updates.
- [ ] Commits: `feat(frontend): scaffold dashboard with typed API client`, `feat(frontend): add live ReAct trace and approval workflow`, `feat(frontend): add operations board and memory viewer`, `build: serve dashboard via nginx in compose`.

### Task 14: Evaluation

**Files:** `backend/app/evaluation/{scenarios,runner,metrics,report}.py`, `backend/tests/unit/test_metrics.py`, `backend/scripts/{run_eval,demo_memory_persistence,demo_approval}.py`, `docs/traces/`, `docs/evaluation.md`
**Produces:** 8 `Scenario`s (spec §6.10); `run_scenario(scenario, deps) -> Trace`; metrics `plan_valid, steps, unnecessary_tool_calls (duplicate same name+args, or irrelevant resource), approval_respected, latency_s, tokens`; report writer (Markdown table).
- [ ] Unit test the metrics on synthetic traces (duplicate-call detection).
- [ ] Run against Groq; commit traces + report with a written failure analysis.
- [ ] Commits: `feat(eval): add scenario runner and agent metrics`, `docs: add evaluation report and scenario traces`.

### Task 15: Final documentation

**Files:** `README.md` (overview, quick start, screenshots, PDF task → file map), `docs/architecture.md`, `docs/tools-and-schemas.md`; review all docs.
- [ ] Commit `docs: complete architecture guide and README`.
