# Agent Memory

Ark-Agent has two kinds of memory, both stored in PostgreSQL and both provided by LangGraph.

| | Short-term memory | Long-term memory |
|---|---|---|
| What | The conversation state of one coordinator thread: messages, tool results, current plan | Operational facts: dispatches, reservations, rejections, road reports |
| Scope | One `thread_id` | Shared by every thread and every shift |
| Backend | `PostgresSaver` checkpointer | `PostgresStore`, namespace `("ops", "facts")` |
| Written by | LangGraph, automatically after every graph step | The agent (`remember_fact` tool) and the graph itself (every approval or rejection) |
| Read by | LangGraph when the thread continues | `load_memory` node (facts for the ward in the request) and the `recall_facts` tool |
| Used for | Follow-ups such as *"what about Ward 9 instead?"*, pausing and resuming at the approval checkpoint | *"Depot B reserved 200 L for Ward 7"* is visible to the next shift after a restart |

Both share one `psycopg_pool.ConnectionPool` (`app/memory/factory.py`). `setup()` creates
LangGraph's tables on startup. Unit tests swap in `InMemorySaver` / `InMemoryStore` through the
same factory.

## Fact schema

Facts are validated by `app.domain.MemoryFact` before they are written:

```json
{
  "id": "4c1e…",
  "kind": "reservation",
  "content": "Depot A reserved 800 litres of drinking_water for W-07 (TASK-0001, team TM-01).",
  "ward_id": "W-07",
  "created_at": "2026-11-21T14:05:12Z",
  "source_thread": "shift-1-ward-7"
}
```

`kind` is one of `decision`, `reservation`, `road_report`, `rejection` or `note`.

## Persistence across restarts

`tests/integration/test_memory_persistence.py` writes a fact, closes the pool, reopens new
backends (as a restarted process would) and reads it back. `scripts/demo_memory_persistence.py`
shows the same thing end to end with the agent across two separate processes.
