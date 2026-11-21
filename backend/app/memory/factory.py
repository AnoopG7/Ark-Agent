"""Construction of the agent's memory backends.

* Short-term memory: a LangGraph checkpointer, keyed by ``thread_id`` (one conversation).
* Long-term memory: a LangGraph store holding operational facts across threads and shifts.

The app uses Postgres for both (sharing one connection pool); tests use the in-memory versions.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.base import BaseStore
from langgraph.store.memory import InMemoryStore

from app.core.config import Settings


@dataclass(frozen=True)
class MemoryBackends:
    checkpointer: BaseCheckpointSaver
    store: BaseStore


def in_memory_backends() -> MemoryBackends:
    return MemoryBackends(checkpointer=InMemorySaver(), store=InMemoryStore())


@contextmanager
def open_postgres_backends(settings: Settings, max_pool_size: int = 10) -> Iterator[MemoryBackends]:
    """Open a pooled Postgres checkpointer and store, creating their tables if needed."""
    from langgraph.checkpoint.postgres import PostgresSaver
    from langgraph.store.postgres import PostgresStore
    from psycopg.rows import dict_row
    from psycopg_pool import ConnectionPool

    pool = ConnectionPool(
        settings.psycopg_url,
        min_size=1,
        max_size=max_pool_size,
        kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
        open=True,
    )
    try:
        checkpointer = PostgresSaver(pool)
        store = PostgresStore(pool)
        checkpointer.setup()
        store.setup()
        yield MemoryBackends(checkpointer=checkpointer, store=store)
    finally:
        pool.close()
