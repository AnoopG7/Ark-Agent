# Ark-Agent

**A ReAct planning agent for the Driftwood Bay Flood Relief Coordination Centre.**
LLM, RAG & Agentic AI · Case Study 90 · *Reasons, acts and remembers across a relief operation.*

A coordinator types *"Ward 7 needs drinking water for 300 people by evening"*. Ark then:

1. **Remembers** what earlier shifts decided about Ward 7 (long-term memory in Postgres).
2. **Reasons and acts** in a ReAct loop: it looks up the SOP for water per person (RAG over
   pgvector), checks stock at three depots, road status and volunteer teams.
3. **Plans around problems**: the shortest road is blocked, so it splits the load across two
   depots over open routes.
4. **Validates** the plan against live data and SOP rules, then **pauses for the coordinator's
   approval** before anything is reserved or any team moves.
5. **Records** the decision so the next shift sees it, even after a restart.

## Stack

| | |
|---|---|
| Agent | LangGraph `StateGraph` (custom ReAct nodes, `interrupt()` human checkpoint, step limit) |
| LLM | Groq `llama-3.3-70b-versatile` with tool calling |
| RAG | 9 relief SOPs → heading-aware chunks → local `bge-small-en-v1.5` embeddings → pgvector (HNSW) |
| Memory | LangGraph `PostgresSaver` (per conversation) + `PostgresStore` (facts across shifts) |
| Backend | Python 3.12 · uv · FastAPI (SSE) · SQLAlchemy 2 · Alembic · Pydantic v2 |
| Frontend | React 19 · TypeScript · Vite · Tailwind CSS |
| Infra | Docker Compose: `db` (Postgres 16 + pgvector), `backend`, `frontend` (nginx) |

## Quick start

```bash
cp .env.example .env              # add GROQ_API_KEY
docker compose up --build
```

Open the dashboard at <http://localhost:8080> (API docs at <http://localhost:8000/docs>).
Development setup, tests and demos are in [docs/setup.md](docs/setup.md).

## Case study tasks → where they are

| PDF task | Implementation | Evidence |
|----------|----------------|----------|
| 1. Mock tools over JSON/SQLite: 3 depots, 6 routes, teams, task creator | `backend/app/db/seed/*.json` → Postgres; `app/tools/` | `tests/unit/test_tools.py`, `tests/contract/ops_repo_contract.py` |
| 2. LangGraph graph with reasoning, tool and finalisation nodes; diagram and edges explained | `app/agent/graph.py`, `nodes.py`, `routing.py` | [docs/graph.md](docs/graph.md), `tests/unit/test_graph.py` |
| 3. Short-term memory (checkpointer) and long-term store persisting across restarts | `app/memory/` | [docs/memory.md](docs/memory.md), `scripts/demo_memory_persistence.py`, `tests/integration/test_memory_persistence.py` |
| 4. Human-in-the-loop interrupt before dispatch; pause and resume | `AgentNodes.approval` | `scripts/demo_approval.py`, dashboard approval slip |
| 5. ≥ 6 scenarios incl. blocked road, insufficient stock, step limit, with traces | `app/evaluation/scenarios.py` (8 scenarios) | [docs/traces/](docs/traces/) |
| 6. Evaluate plan validity, steps, unnecessary tool calls; discuss a failure | `app/evaluation/metrics.py`, `app/agent/validator.py` | [docs/evaluation.md](docs/evaluation.md) |
| Extension: RAG with citations | `app/rag/`, `app/knowledge/` | [docs/rag.md](docs/rag.md) |
| Extension: dashboard | `frontend/` | screenshots below |

## Repository layout

```
backend/    FastAPI + LangGraph service (uv project)
  app/        domain · db · repositories · rag · memory · tools · agent · api · evaluation
  migrations/ Alembic
  scripts/    demos, evaluation runner, graph export
  tests/      unit (offline) · integration (Postgres) · shared contract tests
frontend/   React + TypeScript dashboard
docs/       design, architecture, graph, memory, RAG, database, API, evaluation, traces
```

## Documentation

- [Design document](docs/design/ark-agent-design.md) and [implementation plan](docs/design/ark-agent-implementation-plan.md)
- [Architecture](docs/architecture.md) · [Agent graph](docs/graph.md) · [Memory](docs/memory.md) · [RAG](docs/rag.md)
- [Database](docs/database.md) · [Tools and schemas](docs/tools-and-schemas.md) · [HTTP API](docs/api.md)
- [Setup](docs/setup.md) · [Evaluation](docs/evaluation.md)

## Tests

```bash
cd backend
uv run pytest                  # unit tests: offline, fake LLM, in-memory storage
uv run pytest -m integration   # Postgres: migrations, repository contract, pgvector, memory
```
