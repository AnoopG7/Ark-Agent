"""Long-term facts and conversation checkpoints survive closing and reopening the backends,
which is what happens when the backend process restarts between shifts."""

import pytest

from app.core.config import Settings
from app.domain import MemoryFact
from app.memory.factory import open_postgres_backends
from app.memory.facts import FactsService

pytestmark = pytest.mark.integration


def test_facts_persist_across_reopen(test_database_url: str) -> None:
    settings = Settings(_env_file=None, database_url=test_database_url)
    with open_postgres_backends(settings) as backends:
        facts = FactsService(backends.store, namespace=("test", "facts"))
        facts.clear()
        facts.save(MemoryFact(kind="reservation", content="Depot B reserved 200 L", ward_id="W-07"))

    with open_postgres_backends(settings) as backends:
        facts = FactsService(backends.store, namespace=("test", "facts"))
        found = facts.list(ward_id="W-07")
        assert [f.content for f in found] == ["Depot B reserved 200 L"]
        facts.clear()


def test_checkpointer_tables_created(test_database_url: str) -> None:
    settings = Settings(_env_file=None, database_url=test_database_url)
    with open_postgres_backends(settings) as backends:
        assert list(backends.checkpointer.list({"configurable": {"thread_id": "nope"}})) == []
