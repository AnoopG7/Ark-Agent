# Setup & Running

## Prerequisites

| Tool | Version | Used for |
|------|---------|----------|
| Docker Desktop | 24+ (Compose v2) | PostgreSQL + pgvector, and the full stack |
| uv | 0.5+ | Python 3.12 environment for local backend development |
| Node.js | 20+ | Dashboard development |
| Groq API key | free tier works | The LLM (<https://console.groq.com/keys>) |

## 1. Configure

```bash
cp .env.example .env
# edit .env and set GROQ_API_KEY=gsk_...
```

## 2a. Run everything with Docker Compose

```bash
docker compose up --build
```

| Service | URL |
|---------|-----|
| Dashboard (nginx) | <http://localhost:8080> |
| API + OpenAPI docs | <http://localhost:8000/docs> |
| PostgreSQL | `localhost:5432` (user / password / db: `ark`) |

On first start the backend runs migrations, seeds the operational data, embeds the SOP
knowledge base into pgvector and creates the LangGraph memory tables. The embedding model
(`bge-small-en-v1.5`, ~65 MB) is cached in `backend/.fastembed_cache`, which is mounted into the
container so it downloads only once.

## 2b. Run for development (hot reload)

```bash
docker compose up -d db                       # database only

cd backend
uv sync                                       # creates backend/.venv from uv.lock
uv run uvicorn app.api.main:app --reload      # http://localhost:8000

cd ../frontend
npm install
npm run dev                                   # http://localhost:5173 (proxies /api to :8000)
```

## 3. Tests and quality checks

```bash
cd backend
uv run pytest                     # offline unit suite (in-memory repos, fake LLM)
uv run pytest -m integration      # against Postgres (needs `docker compose up -d db`)
uv run ruff check . && uv run ruff format --check .

cd ../frontend
npm run lint && npm run build
```

## 4. Demos and evaluation

```bash
cd backend
uv run python -m scripts.demo_approval            # pause at the approval checkpoint, then resume
uv run python -m scripts.demo_memory_persistence  # facts survive a process restart
uv run python -m scripts.run_eval                 # scenario traces + docs/evaluation.md
```

## Troubleshooting

- **`error: GROQ_API_KEY is not set`** in the dashboard: add the key to `.env` and restart the
  backend (`docker compose restart backend`).
- **Port 5432 already in use**: set `POSTGRES_PORT=5433` in `.env` and update `DATABASE_URL`.
- **Reset the demo**: *Reset data* in the dashboard (or `POST /api/ops/reset`) restores stock,
  roads and teams; *Clear memory* empties long-term facts. `docker compose down -v` wipes the
  database entirely.
