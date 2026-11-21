from datetime import UTC, datetime, timedelta

import pytest
from langgraph.store.memory import InMemoryStore

from app.domain import FactKind, MemoryFact
from app.memory.facts import FactsService
from app.repositories.memory_ops import InMemoryOpsRepository
from app.tools.context import ToolContext
from app.tools.executor import run_tool
from app.tools.registry import build_tools


@pytest.fixture
def facts() -> FactsService:
    return FactsService(InMemoryStore())


def test_save_and_list_newest_first(facts: FactsService) -> None:
    now = datetime.now(UTC)
    facts.save(MemoryFact(kind="note", content="old note", created_at=now - timedelta(hours=1)))
    facts.save(MemoryFact(kind="reservation", content="Depot B reserved 200 L", ward_id="W-07"))
    assert [f.content for f in facts.list()] == ["Depot B reserved 200 L", "old note"]


def test_filters(facts: FactsService) -> None:
    facts.save(MemoryFact(kind="reservation", content="water for ward 7", ward_id="W-07"))
    facts.save(MemoryFact(kind="road_report", content="RT-05 waterlogged", ward_id="W-07"))
    facts.save(MemoryFact(kind="reservation", content="boats for ward 9", ward_id="W-09"))
    assert len(facts.list(ward_id="W-07")) == 2
    assert [f.content for f in facts.list(ward_id="W-07", kind=FactKind.ROAD_REPORT)] == [
        "RT-05 waterlogged"
    ]
    assert facts.clear() == 3 and facts.list() == []


def test_memory_tools_roundtrip_with_thread_id(facts: FactsService) -> None:
    tools = {t.name: t for t in build_tools(ToolContext(repo=InMemoryOpsRepository(), facts=facts))}
    saved = run_tool(
        tools["remember_fact"],
        {"kind": "road_report", "content": "Ridge Road has a fallen tree", "ward_id": "W-07"},
        config={"configurable": {"thread_id": "shift-1"}},
    )
    assert saved.ok and saved.data["saved"]["source_thread"] == "shift-1"
    recalled = run_tool(tools["recall_facts"], {"ward_id": "W-07"})
    assert recalled.data["facts"][0]["content"] == "Ridge Road has a fallen tree"
    assert not run_tool(tools["remember_fact"], {"kind": "gossip", "content": "hello"}).ok
