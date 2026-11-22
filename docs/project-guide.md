# Ark: the complete project guide

This guide explains the whole project from scratch: what problem it solves, how a request flows
through the system, what every feature does, where the code lives, and how to demo and defend it.
Read it top to bottom once; afterwards use the headings as a reference.

---

## 1. The problem in one paragraph

Driftwood Bay is flooded. A coordination centre receives requests like *"Ward 7 needs drinking
water for 300 people by evening"*. Answering one request well means checking several things:
how much water 300 people need (an SOP rule), which depots have stock, which roads to Ward 7 are
open, and which volunteer team is free and has the right skills and vehicle. A wrong answer is
costly (sending a truck down a flooded road), so a **human coordinator must approve** before
anything is sent. **Ark** is an AI planning agent that does this checking for the coordinator,
proposes a plan, waits for approval, and remembers what happened for the next shift.

This is **Case Study 90** of the course. The PDF asked for six tasks; we added two extensions
(RAG and a web dashboard). Section 9 maps every task to the code.

---

## 2. Five ideas you need to understand

### 2.1 ReAct (Reason + Act)
Instead of answering in one shot, the LLM works in a loop:

```
Thought:  "I need to know the water allowance per person."
Action:   search_guidelines("drinking water per person per day")
Observation: "3 litres per person per day (sop-water-supply.md#daily-allowance)"
Thought:  "300 people x 3 L = 900 L. Now check stock."
Action:   stock_lookup("drinking_water")
...
```

Each turn of the loop is one **step**. The model decides which tool to call next based on what it
has observed so far. This is why the middle panel of the dashboard shows numbered steps.

### 2.2 LangGraph
LangGraph lets us write the agent as a **graph** of nodes (Python functions) connected by edges.
Our graph:

```
START -> load_memory -> reason --(tool calls)--> tools --> reason   (the ReAct loop)
                          |
                          +--(wants to dispatch)--> approval --approve/reject--> finalize_plan -> END
                          |                            |
                          |                            +--revise--> reason
                          +--(final answer or step limit)--> finalize_plan -> END
```

| Node | What it does |
|------|--------------|
| `load_memory` | Start of each request: resets the step counter and loads remembered facts about the wards mentioned |
| `reason` | Calls the LLM with the system prompt + conversation; the LLM either calls tools or answers |
| `tools` | Runs the read-only tools the LLM asked for and adds their results to the conversation |
| `approval` | Validates the proposed plan, then **pauses the graph** (`interrupt()`) until the coordinator decides |
| `finalize_plan` | Writes the final message (dispatched / rejected / answered / step limit reached) |

The dashed arrows in the Graph tab are **conditional edges**: `routing.py` decides where to go
after `reason` (tools, approval or finalize) and after `approval` (back to reason or finalize).

### 2.3 Human-in-the-loop (HITL)
The only tool that changes the world is `create_dispatch_task`. The graph **never runs it
directly**. When the LLM calls it, the graph:

1. Validates the plan against live data and SOP rules (`validator.py`). If it is invalid, the
   errors go back to the LLM to fix; the coordinator never sees a broken plan.
2. Calls `interrupt()`: execution stops and the plan is saved in Postgres. The dashboard shows
   the yellow **dispatch slip**.
3. Waits. The coordinator can:
   - **Approve**: stock is reserved, the team is marked deployed, a `TASK-xxxx` is created.
   - **Send back with note**: the note goes to the LLM, which revises the plan (loop again).
   - **Reject**: recorded, nothing reserved.

Because the paused state lives in the database, you can close the browser or even restart the
backend and the approval is still waiting.

### 2.4 Memory (short-term and long-term)
- **Short-term memory = the conversation.** LangGraph's `PostgresSaver` (a "checkpointer") saves
  the full state of each conversation thread after every node. That is why a follow-up like
  *"and Ward 9 too"* works, and why reloading the page restores the chat.
- **Long-term memory = facts across conversations and shifts.** LangGraph's `PostgresStore` keeps
  facts such as *"TASK-0002 dispatched to W-07 ..."* or *"DEP-A reserved 800 L ..."*. Every new
  request reads the facts for the wards it mentions (`load_memory`), so the next shift's
  conversation knows what was already sent. Shown in the **Memory** tab.

### 2.5 RAG (Retrieval-Augmented Generation)
The relief rules (water per person, medicine kits per 50 people, boat capacity...) are written as
9 SOP markdown files in `backend/app/knowledge/`. At startup they are:

1. **Chunked** by heading (`rag/chunker.py`),
2. **Embedded** into 384-number vectors by a small local model, `bge-small-en-v1.5` (no API needed),
3. **Stored** in Postgres with the **pgvector** extension (HNSW index for fast similarity search).

When the agent calls `search_guidelines("water per person")`, the query is embedded and the most
similar chunks are returned with a **citation** like `sop-water-supply.md#daily-allowance`.
Results below a similarity of 0.60 are dropped so the agent doesn't get irrelevant text. Plans
must cite the guideline they relied on; the slip shows it as "Based on ...".

---

## 3. The world Ark works in (seed data)

Stored in `backend/app/db/seed/*.json`, loaded into Postgres on first start.

**Depots (stock):**

| | Water (L) | Food | Medicine kits | Boats | Shelter kits | Blankets |
|---|---|---|---|---|---|---|
| DEP-A Hilltop | 800 | 400 | 40 | 2 | 60 | 300 |
| DEP-B Central Market | 1,500 | 600 | 50 | 4 | 100 | 500 |
| DEP-C Harbour | 600 | 250 | 30 | 6 | 40 | 200 |

**Routes (the interesting ones):**

| Route | From → To | Status | Time | Why it matters |
|---|---|---|---|---|
| RT-03 | DEP-B → Ward 7 | **blocked** (bridge submerged) | 30 min | Shortest road, but unusable |
| RT-01 | DEP-A → Ward 7 | open | 75 min | Only 800 L at DEP-A |
| RT-05 | DEP-C → Ward 7 | slow | 120 min | Needed to top up |
| RT-04 | DEP-B → Ward 9 | boat-only | | Needs a boat crew |
| RT-02 | DEP-A → Ward 3 | open | | Routine case |
| RT-06 | DEP-C → Ward 12 | open | 35 min | Only route to Ward 12 |

**Teams:** TM-01 to TM-08 with skills (logistics, medical, boat_rescue, shelter), a vehicle
(truck or boat) and a status. TM-05 starts deployed and TM-07 resting, so they can't be used.

**12 wards** with populations. The data is deliberately designed so that the "obvious" plan
for Ward 7 fails (blocked road) and Ward 12 medicine can't be fully covered.

---

## 4. The agent's tools

| Tool | What the agent uses it for | Changes data? |
|------|----------------------------|---------------|
| `search_guidelines` | RAG search of the SOPs; returns passages + citations | No |
| `situation_report` | One call with stock per depot, every route to the ward and suitable available teams (the usual first lookup) | No |
| `stock_lookup` | Stock per depot for a resource (quantity, reserved, available) | No |
| `road_status` | Routes to a ward, sorted by time, with a `usable` flag | No |
| `list_teams` | Available teams, filter by skill | No |
| `recall_facts` | Read long-term memory | No |
| `remember_fact` | Save a note to long-term memory | Writes memory |
| `create_dispatch_task` | Propose the final plan | **Only after approval** |

Every tool returns a typed `ToolResult` (`ok` + `data`, or `error`). Errors (unknown ward, bad
arguments) are given back to the LLM as observations instead of crashing the run.

**Validation rules** checked before the coordinator sees a plan (`agent/validator.py`):
ward and team exist; team is available and has the right skill (medicine → medical); each route
really connects that depot to that ward and is not blocked; boat-only routes need a boat crew;
the depot has the stock; the quantity meets the SOP minimum; ETA is not shorter than the slowest
route; the plan cites a guideline that was actually retrieved.

---

## 5. Walkthrough: one request end to end

*"Ward 7 needs drinking water for 300 people by evening"*

1. The browser `POST`s the message to `/api/threads/{id}/messages`. The response is a **Server-Sent
   Events stream**, so each step appears live.
2. `load_memory` finds nothing about Ward 7 yet.
3. **Step 1:** LLM calls `search_guidelines` → 3 L/person/day → needs 900 L.
4. **Step 2:** `situation_report` for W-07 → stock A 800, B 1,500, C 600; RT-03 blocked, RT-01
   open, RT-05 slow; available teams.
5. **Step 3:** LLM calls `create_dispatch_task` (800 L from DEP-A + 100 L from DEP-C) → validator
   passes → **interrupt**. Slip appears.
6. Coordinator approves → Postgres transaction locks the stock rows (`SELECT ... FOR UPDATE`),
   reserves stock, sets the team to deployed, creates `TASK-0001`, and saves facts to memory.
7. `finalize_plan` writes "Approved and dispatched...". Depot bars turn amber for the reserved part.

The step limit (default 8) stops a confused agent from looping forever; if reached, Ark says
what it found so far and stops (scenario S4).

---

## 6. The dashboard, panel by panel

**Header:** green dots show the database is connected and which LLM is configured.
*New conversation* starts a fresh thread (long-term memory is kept). *Reset demo data* restores
seed stock, routes and teams and clears dispatches and long-term memory (the RAG index is kept).

**Left: Requests (chat).** Type a request or click an example to fill the box. Shows your
messages, Ark's answers, decision notes, and the **dispatch slip** when approval is needed:
- table of depot / route / quantity legs, team, ETA, needed vs allocated,
- red banner if there is a shortfall,
- the agent's rationale and the SOP citation,
- note box + **Approve dispatch / Send back with note / Reject**.

**Middle: How Ark is planning (live trace).** One numbered card per ReAct step: the model's
thought in italics, each tool call in plain English ("Check roads, Routes to Ward 7") and a
short summary of the result. Badges: *done*, *running*, *awaiting approval*, *sent back*,
*rejected*, *problem*. The header shows "Step N of 8" and the run status.

**Right: Operations board (tabs).**
- **Depots:** stock bars per depot; amber = reserved by approved dispatches. Refreshes every 15 s
  and after each run.
- **Roads:** every route with a status dropdown. Changing it simulates a field report (e.g. mark
  RT-01 blocked and ask again; the agent will route around it). The red badge counts blocked roads.
- **Teams:** skills, vehicle, base depot, status (available / deployed / resting).
- **Dispatches:** every decision (`TASK-xxxx`), dispatched or rejected, with the note.
- **Memory:** long-term facts Ark will read next time, with a *Clear memory* button.
- **Graph:** the live LangGraph diagram, generated from the actual compiled graph.

---

## 7. Architecture and tech stack

```
Browser (React dashboard, :8080)
   |  HTTP + Server-Sent Events
nginx (serves the built React app, proxies /api)
   |
FastAPI backend (:8000)  ----->  Groq API (LLM: openai/gpt-oss-120b)
   |   LangGraph agent, tools, RAG, validator
   |
PostgreSQL 16 + pgvector (one database for everything)
   - ops tables: wards, depots, stock, routes, teams, dispatch tasks, reservations
   - guideline_chunks: SOP text + 384-d vectors (RAG)
   - LangGraph checkpoint tables (short-term memory)
   - LangGraph store table (long-term memory)
```

| Layer | Tech | Why |
|------|------|-----|
| LLM | Groq, `openai/gpt-oss-120b` | Free, very fast, supports tool calling |
| Agent | LangGraph 1.x | Explicit graph, built-in checkpointing and `interrupt()` |
| Backend | Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2, Alembic, uv | Typed schemas end to end, migrations, reproducible env |
| Vectors | pgvector (HNSW, cosine) | No separate vector DB needed |
| Embeddings | fastembed `bge-small-en-v1.5` (local) | No API cost, works offline |
| Frontend | React 19, TypeScript, Vite, Tailwind v4 | Typed API client, fast build |
| Infra | Docker Compose (db, backend, frontend) | One command to run everything |

### Backend folders (`backend/app/`)

| Folder | Responsibility |
|--------|----------------|
| `core/` | Settings from `.env` (`config.py`) |
| `domain/` | Pydantic models: Ward, Depot, Route, Team, ReliefPlan, DispatchTask, MemoryFact, ToolResult |
| `db/` | ORM models, session, seed JSON + loader, seeder |
| `repositories/` | Data access behind one interface; SQL version for production, in-memory version for tests; shared business rules |
| `knowledge/` | The 9 SOP markdown files |
| `rag/` | Chunker, embedder, pgvector index, ingestion, retriever |
| `memory/` | Checkpointer/store factory, long-term facts service |
| `tools/` | The 7 agent tools and their schemas |
| `agent/` | Prompt, LLM setup with retries, nodes, routing, graph, validator, diagram |
| `api/` | FastAPI app, routers, SSE streaming, dependency container |
| `evaluation/` | Scenarios, runner, metrics, report writer |

Other: `migrations/` (database schema versions), `scripts/` (demos and evaluation),
`tests/` (unit tests with a fake LLM, integration tests against real Postgres).

### Frontend folders (`frontend/src/`)
`api/client.ts` (typed REST + SSE parser), `types/api.ts` (mirrors backend schemas),
`hooks/useAgentThread.ts` (chat, trace, approval state), `hooks/useOps.ts` (board polling),
`components/` (Header, ChatPanel, ApprovalSlip, TracePanel, OpsPanel and the six tabs),
`lib/` (formatting helpers).

---

## 8. Quality and reliability features (good points for a viva)

- **Strong schemas:** every model forbids unknown fields, IDs follow patterns (`W-07`, `DEP-A`,
  `TASK-0001`), quantities have bounds. Bad LLM output is rejected and explained back to it.
- **No double booking:** approval runs in one transaction with row locks plus database CHECK
  constraints (`reserved <= quantity`).
- **Nothing written before approval:** the pause happens before any write.
- **Retries:** Groq rate limits and malformed tool calls are retried with exponential backoff;
  an empty model turn is re-asked.
- **Step limit:** stops runaway loops.
- **Speed:** every step resends the whole conversation, so tokens grow with each step and the
  free Groq tier (8,000 tokens/minute) is the bottleneck, not the model (each call takes ~0.5 s).
  We cut a plan from ~7 steps to ~3 with the combined `situation_report` tool, set gpt-oss
  reasoning effort to low, and tell the model never to repeat a call. A paid Groq tier (much
  higher token limit) would bring a run down to a few seconds without code changes.
- **Tests:** 121 offline unit tests (fake scripted LLM, in-memory storage) and 25 integration
  tests on real Postgres. One contract test suite runs against both repository implementations
  so they behave identically.
- **Docs:** `docs/` has architecture, graph, memory, RAG, database (ER diagram), API, setup.

---

## 9. Case-study tasks → where they are

| PDF task | Where |
|----------|-------|
| 1. Mock tools (3 depots, 6 routes, teams, task creator) | `db/seed/`, `tools/`, `repositories/` |
| 2. LangGraph with reason/tool/finalise nodes + diagram | `agent/graph.py`, `nodes.py`, `routing.py`; `docs/graph.md`; Graph tab |
| 3. Short-term (checkpointer) + long-term store across restarts | `memory/`; `scripts/demo_memory_persistence.py` |
| 4. Human approval interrupt before dispatch | `AgentNodes.approval`; dispatch slip; `scripts/demo_approval.py` |
| 5. ≥6 scenarios incl. blocked road, insufficient stock, step limit | `evaluation/scenarios.py` (8 scenarios, below) |
| 6. Evaluate validity, steps, unnecessary calls; discuss a failure | `evaluation/metrics.py`, `validator.py`; evaluation report (next step) |
| Extensions | RAG (`rag/`, `knowledge/`), dashboard (`frontend/`) |

**The 8 scenarios:** S1 routine (Ward 3 food) · S2 preferred road blocked (Ward 7 water) ·
S3 insufficient stock everywhere (Ward 12 medicine) · S4 step limit (limit set to 3) ·
S5 follow-up using conversation memory (Ward 9 after a reject) · S6 coordinator sends plan back ·
S7 next shift remembers (long-term memory) · S8 guideline-driven quantity (shelter kits via RAG).

**Metrics:** plan validity (re-checked with the validator), steps used, duplicate tool calls
(same tool, same args, same turn), irrelevant calls (stock lookups for resources not needed).

**A real failure we already observed (good for the task-6 discussion):** on Ward 12 medicine the
model invented a rule that a team can only use routes from its own home depot, concluded no
team could reach Ward 12 and refused to plan. Fix: the prompt now states that a team's base
depot does not restrict it, and that partial plans must still be submitted for approval. After
the fix it proposed 30 kits via RT-06 with a 130-kit shortfall flagged.

---

## 10. Running it

```bash
docker compose up -d          # start db, backend, frontend (Docker Desktop must be running)
open http://localhost:8080    # dashboard
open http://localhost:8000/docs   # interactive API docs
docker compose logs -f backend    # watch the agent's LLM calls
docker compose down           # stop (data is kept in a Docker volume)
```

The Groq key lives in `.env` (`GROQ_API_KEY`). After changing `.env` run
`docker compose up -d backend` (a plain restart does not reload it).

Terminal demos (from `backend/`): `uv run python -m scripts.demo_approval`,
`uv run python -m scripts.demo_memory_persistence`, `uv run python -m scripts.run_eval S2`.
Tests: `uv run pytest` and `uv run pytest -m integration`.

Free Groq limit: 8,000 tokens/minute. If a run seems to pause for ~20 s, it is waiting out the
rate limit and will continue on its own. See §8 for why a run takes ~45 s and how to speed it up.

---

## 11. Demo video script (about 5 minutes)

Before recording: *Reset demo data* (also clears memory) and *New conversation*.

| # | Do | Say |
|---|----|-----|
| 1 | Show the full dashboard | "Ark is a ReAct planning agent for flood relief. Left: requests. Middle: the agent's reasoning live. Right: the live operations data in Postgres." |
| 2 | Roads tab, point at RT-03 | "The shortest road to Ward 7 is blocked. The agent has to discover that itself." |
| 3 | Send "Ward 7 needs drinking water for 300 people by evening" | "Each card is one ReAct step: a thought, a tool call, the observation." |
| 4 | Point at step 1 citation | "It retrieves the SOP with RAG: 3 litres per person, so 900 L. The citation is shown." |
| 5 | Point at roads step | "It sees RT-03 is blocked and avoids it." |
| 6 | Slip appears | "Before anything is dispatched the graph pauses with interrupt(). Nothing is reserved yet." |
| 7 | If there is a shortfall, type a note and *Send back* (else skip) | "The coordinator can send it back; the note goes to the agent, which revises the plan." |
| 8 | *Approve dispatch* | "Now stock is reserved in one transaction and the team is deployed." |
| 9 | Depots (amber), Teams, Dispatches, Memory tabs | "Reserved stock, deployed team, the task record, and facts saved to long-term memory." |
| 10 | *New conversation*, send "What has already been sent to Ward 7?" | "A brand-new conversation, but long-term memory tells it what the last shift did." |
| 11 | *New conversation*, send "Ward 12 needs medicine kits for 8,000 people" | "Only 30 kits can reach Ward 12. It proposes a partial plan and flags the 130-kit shortfall." |
| 12 | Type a note, *Reject* | "Rejected: recorded, nothing reserved." |
| 13 | Graph tab | "This is the actual LangGraph: load memory, reason, tools loop, approval checkpoint, finalize." |
| 14 | Optional terminal: `docker compose restart backend`, reload page | "Conversation and memory are in Postgres, so they survive a restart." |

---

## 12. Likely viva questions

- **Why LangGraph and not a plain loop?** Checkpointing, `interrupt()` for human approval, and an
  explicit, testable graph with conditional edges.
- **Where is short-term vs long-term memory?** Checkpointer (per thread, every step) vs store
  (facts across threads), both in Postgres.
- **How do you stop the LLM from doing something dangerous?** It can only read; the one writing
  tool is routed to a validated human approval, and the database enforces stock constraints.
- **What if the LLM hallucinates a depot or route?** Pydantic schemas and the validator reject it
  and the error is fed back as an observation.
- **Why pgvector instead of a vector DB?** One database for ops data, vectors and memory; simpler
  to run, transactional, enough for 9 documents.
- **How do you test an LLM agent?** A scripted fake LLM makes graph tests deterministic and
  offline; the evaluation runner measures the real model on 8 scenarios.
- **What happens when the road status changes mid-shift?** Change it in the Roads tab; tools read
  live data so the next plan routes around it, and the validator rejects plans using it.
