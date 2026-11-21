import json

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.memory import InMemoryStore
from langgraph.types import Command

from app.agent.graph import build_graph
from app.core.config import get_settings
from app.domain import ResourceType, TaskStatus, TeamStatus
from app.memory.facts import FactsService
from app.rag.embeddings import HashEmbedder
from app.rag.ingest import sync_knowledge
from app.rag.memory_index import InMemoryVectorIndex
from app.rag.retriever import Retriever
from app.repositories.memory_ops import InMemoryOpsRepository
from tests.fakes import FakeToolCallingModel, ai, call

WATER_PLAN = {
    "ward_id": "W-07",
    "resource": "drinking_water",
    "people": 300,
    "quantity_required": 900,
    "allocations": [
        {"depot_id": "DEP-A", "resource": "drinking_water", "quantity": 800, "route_id": "RT-01"},
        {"depot_id": "DEP-C", "resource": "drinking_water", "quantity": 100, "route_id": "RT-05"},
    ],
    "team_id": "TM-01",
    "eta_minutes": 135,
    "rationale": "RT-03 is blocked so water comes from DEP-A and DEP-C.",
    "citations": ["sop-water-supply.md#daily-allowance"],
}


@pytest.fixture
def repo() -> InMemoryOpsRepository:
    return InMemoryOpsRepository()


@pytest.fixture
def store() -> InMemoryStore:
    return InMemoryStore()


@pytest.fixture(scope="module")
def retriever() -> Retriever:
    index = InMemoryVectorIndex()
    sync_knowledge(get_settings().knowledge_dir, HashEmbedder(), index)
    return Retriever(HashEmbedder(), index, min_score=0.0)


def make_graph(responses, repo, store, retriever, max_steps=8):
    llm = FakeToolCallingModel(responses=list(responses))
    graph = build_graph(
        llm=llm,
        repo=repo,
        checkpointer=InMemorySaver(),
        store=store,
        retriever=retriever,
        max_steps=max_steps,
    )
    return graph, llm


def cfg(thread: str = "t1", **extra) -> dict:
    return {"configurable": {"thread_id": thread, **extra}}


def ask(graph, text: str, thread: str = "t1", **extra):
    return graph.invoke({"messages": [HumanMessage(text)]}, cfg(thread, **extra))


def assert_history_valid(messages) -> None:
    """Every tool call has exactly one ToolMessage answering it."""
    calls = [c["id"] for m in messages if isinstance(m, AIMessage) for c in m.tool_calls]
    answers = [m.tool_call_id for m in messages if isinstance(m, ToolMessage)]
    assert sorted(calls) == sorted(answers)


def planning_script():
    return [
        ai(call("search_guidelines", query="drinking water litres per person per day")),
        ai(
            call("stock_lookup", resource="drinking_water"),
            call("road_status", ward_id="W-07"),
            call("list_teams", skill="logistics"),
        ),
        ai(call("create_dispatch_task", **WATER_PLAN), text="Thought: propose split plan"),
    ]


def test_read_only_loop_then_answer(repo, store, retriever) -> None:
    graph, llm = make_graph(
        [ai(call("road_status", ward_id="W-07")), AIMessage(content="RT-03 is blocked.")],
        repo,
        store,
        retriever,
    )
    out = ask(graph, "Is the road to Ward 7 open?")
    assert out["status"] == "answered"
    assert out["step_count"] == 2
    assert out["messages"][-1].content == "RT-03 is blocked."
    tool_msg = next(m for m in out["messages"] if isinstance(m, ToolMessage))
    assert json.loads(tool_msg.content)["ok"] is True
    assert_history_valid(out["messages"])


def test_dispatch_requires_interrupt(repo, store, retriever) -> None:
    graph, _ = make_graph(planning_script(), repo, store, retriever)
    out = ask(graph, "Ward 7 needs drinking water for 300 people by evening")
    interrupts = out["__interrupt__"]
    assert interrupts[0].value["type"] == "dispatch_approval"
    assert interrupts[0].value["plan"]["team_id"] == "TM-01"
    # Nothing written before approval.
    assert repo.list_tasks() == []
    assert repo.get_stock(ResourceType.DRINKING_WATER, "DEP-A")[0].reserved == 0


def test_approve_reserves_stock_and_remembers(repo, store, retriever) -> None:
    graph, _ = make_graph(planning_script(), repo, store, retriever)
    ask(graph, "Ward 7 needs drinking water for 300 people by evening")
    out = graph.invoke(Command(resume={"decision": "approve", "note": "go"}), cfg())
    assert out["status"] == "dispatched"
    assert "TASK-0001 dispatched" in out["messages"][-1].content
    task = repo.list_tasks()[0]
    assert task.status is TaskStatus.DISPATCHED and task.thread_id == "t1"
    assert repo.get_stock(ResourceType.DRINKING_WATER, "DEP-A")[0].reserved == 800
    team = next(t for t in repo.list_teams() if t.id == "TM-01")
    assert team.status is TeamStatus.DEPLOYED
    facts = FactsService(store).list(ward_id="W-07")
    assert {f.kind for f in facts} == {"decision", "reservation"}
    assert_history_valid(out["messages"])


def test_reject_records_and_reserves_nothing(repo, store, retriever) -> None:
    graph, _ = make_graph(planning_script(), repo, store, retriever)
    ask(graph, "Ward 7 needs drinking water for 300 people by evening")
    out = graph.invoke(Command(resume={"decision": "reject", "note": "already covered"}), cfg())
    assert out["status"] == "rejected"
    assert repo.list_tasks()[0].status is TaskStatus.REJECTED
    assert repo.get_stock(ResourceType.DRINKING_WATER, "DEP-A")[0].reserved == 0
    assert FactsService(store).list(kind="rejection")[0].ward_id == "W-07"
    assert_history_valid(out["messages"])


def test_revise_sends_feedback_back_to_reason(repo, store, retriever) -> None:
    script = [*planning_script(), AIMessage(content="Revised: please confirm team TM-06.")]
    graph, llm = make_graph(script, repo, store, retriever)
    ask(graph, "Ward 7 needs drinking water for 300 people by evening")
    out = graph.invoke(Command(resume={"decision": "revise", "note": "use TM-06"}), cfg())
    assert out["status"] == "answered"
    last_prompt = llm.prompts[-1]
    feedback = [m for m in last_prompt if isinstance(m, ToolMessage)][-1]
    assert "use TM-06" in feedback.content
    assert_history_valid(out["messages"])


def test_dispatch_in_parallel_calls_still_interrupts(repo, store, retriever) -> None:
    script = [
        ai(call("search_guidelines", query="drinking water litres per person per day")),
        ai(
            call("stock_lookup", resource="drinking_water"),
            call("create_dispatch_task", **WATER_PLAN),
        ),
    ]
    graph, _ = make_graph(script, repo, store, retriever)
    out = ask(graph, "Ward 7 needs water for 300 people")
    assert "__interrupt__" in out
    assert repo.list_tasks() == []
    out = graph.invoke(Command(resume={"decision": "approve"}), cfg())
    assert out["status"] == "dispatched"
    assert_history_valid(out["messages"])


def test_invalid_plan_never_reaches_coordinator(repo, store, retriever) -> None:
    blocked = {
        **WATER_PLAN,
        "allocations": [
            {
                "depot_id": "DEP-B",
                "resource": "drinking_water",
                "quantity": 900,
                "route_id": "RT-03",
            }
        ],
        "citations": [],
    }
    script = [ai(call("create_dispatch_task", **blocked)), AIMessage(content="Re-planning.")]
    graph, llm = make_graph(script, repo, store, retriever)
    out = ask(graph, "Ward 7 needs water for 300 people")
    assert "__interrupt__" not in out
    err = json.loads([m for m in llm.prompts[-1] if isinstance(m, ToolMessage)][-1].content)
    assert not err["ok"] and "blocked" in err["error"]
    assert_history_valid(out["messages"])


def test_step_limit_routes_to_finalize(repo, store, retriever) -> None:
    script = [ai(call("stock_lookup", resource="boat")) for _ in range(3)]
    graph, _ = make_graph(script, repo, store, retriever)
    out = ask(graph, "Ward 9 needs boats", max_steps=3)
    assert out["status"] == "step_limit"
    assert out["step_count"] == 3
    assert "step limit" in out["messages"][-1].content
    assert_history_valid(out["messages"])


def test_follow_up_uses_thread_context(repo, store, retriever) -> None:
    def answer_with_context(messages):
        humans = [m.content for m in messages if isinstance(m, HumanMessage)]
        return AIMessage(content=" | ".join(humans))

    graph, _ = make_graph(
        [AIMessage(content="Ward 7 plan ready."), answer_with_context], repo, store, retriever
    )
    ask(graph, "Ward 7 needs drinking water for 300 people")
    out = ask(graph, "What about Ward 9 instead?")
    assert "Ward 7 needs drinking water" in out["messages"][-1].content
    assert out["step_count"] == 1  # reset per request


def test_long_term_facts_injected_into_prompt(repo, store, retriever) -> None:
    graph, _ = make_graph(planning_script(), repo, store, retriever)
    ask(graph, "Ward 7 needs drinking water for 300 people")
    graph.invoke(Command(resume={"decision": "approve"}), cfg())

    # A new thread (next shift) with a fresh graph sharing only the store.
    graph2, llm2 = make_graph([AIMessage(content="ok")], repo, store, retriever)
    ask(graph2, "Anything already sent to Ward 7?", thread="shift-2")
    system_prompt = llm2.prompts[0][0].content
    assert "DEP-A reserved 800 drinking_water for W-07" in system_prompt


def test_diagram_contains_all_nodes_and_edges() -> None:
    from app.agent.diagram import graph_mermaid

    mermaid = graph_mermaid()
    for edge in (
        "__start__ --> load_memory",
        "load_memory --> reason",
        "reason -.-> tools",
        "reason -.-> approval",
        "reason -.-> finalize_plan",
        "tools --> reason",
        "approval -.-> reason",
        "approval -.-> finalize_plan",
        "finalize_plan --> __end__",
    ):
        assert edge in mermaid
