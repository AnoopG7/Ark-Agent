import json

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.memory import InMemoryStore

from app.api.container import AppContainer
from app.api.main import create_app
from app.core.config import Settings, get_settings
from app.rag.embeddings import HashEmbedder
from app.rag.ingest import sync_knowledge
from app.rag.memory_index import InMemoryVectorIndex
from app.rag.retriever import Retriever
from app.repositories.memory_ops import InMemoryOpsRepository
from tests.fakes import FakeToolCallingModel, ai, call
from tests.unit.test_graph import WATER_PLAN


def make_client(responses=None, llm=..., settings: Settings | None = None) -> TestClient:
    index = InMemoryVectorIndex()
    sync_knowledge(get_settings().knowledge_dir, HashEmbedder(), index)
    container = AppContainer(
        settings=settings or Settings(_env_file=None),
        repo=InMemoryOpsRepository(),
        checkpointer=InMemorySaver(),
        store=InMemoryStore(),
        retriever=Retriever(HashEmbedder(), index, min_score=0.0),
        llm=FakeToolCallingModel(responses=list(responses or [])) if llm is ... else llm,
    )
    return TestClient(create_app(container))


def parse_sse(text: str) -> list[dict]:
    events = []
    for frame in text.strip().split("\n\n"):
        data = next(line[6:] for line in frame.splitlines() if line.startswith("data: "))
        events.append(json.loads(data))
    return events


def dispatch_script():
    return [
        ai(call("search_guidelines", query="drinking water litres per person per day")),
        ai(call("road_status", ward_id="W-07"), text="Thought: check roads"),
        ai(call("create_dispatch_task", **WATER_PLAN)),
    ]


def test_health_and_reference_data() -> None:
    with make_client() as client:
        health = client.get("/api/health").json()
        assert health == {
            "status": "ok",
            "database": True,
            "llm_configured": True,
            "model": "llama-3.3-70b-versatile",
        }
        assert len(client.get("/api/ops/depots").json()) == 3
        assert len(client.get("/api/ops/routes", params={"ward_id": "W-07"}).json()) == 3
        assert len(client.get("/api/ops/wards").json()) == 12
        assert "load_memory" in client.get("/api/graph").json()["mermaid"]


def test_patch_route_and_reset() -> None:
    with make_client() as client:
        res = client.patch("/api/ops/routes/RT-01", json={"status": "blocked", "note": "tree"})
        assert res.status_code == 200 and res.json()["status"] == "blocked"
        assert client.patch("/api/ops/routes/RT-99", json={"status": "open"}).status_code == 404
        assert client.patch("/api/ops/routes/RT-01", json={"status": "flying"}).status_code == 422
        assert client.post("/api/ops/reset").status_code == 204
        route = client.get("/api/ops/routes", params={"ward_id": "W-07"}).json()
        assert next(r for r in route if r["id"] == "RT-01")["status"] == "open"


def test_full_dispatch_flow_over_sse() -> None:
    with make_client(dispatch_script()) as client:
        tid = client.post("/api/threads").json()["thread_id"]
        res = client.post(
            f"/api/threads/{tid}/messages",
            json={"content": "Ward 7 needs drinking water for 300 people"},
        )
        assert res.headers["content-type"].startswith("text/event-stream")
        events = parse_sse(res.text)
        types = [e["type"] for e in events]
        assert types[0] == "run_started" and types[-1] == "done"
        assert "thought" in types and "tool_call" in types and "tool_result" in types
        interrupt = next(e for e in events if e["type"] == "interrupt")
        assert interrupt["data"]["plan"]["team_id"] == "TM-01"
        assert events[-1]["data"]["status"] == "awaiting_approval"

        state = client.get(f"/api/threads/{tid}").json()
        assert state["status"] == "awaiting_approval"
        assert state["pending_approval"]["plan"]["ward_id"] == "W-07"
        # New messages are refused while a decision is pending.
        blocked = client.post(f"/api/threads/{tid}/messages", json={"content": "hi"})
        assert blocked.status_code == 409

        done = parse_sse(
            client.post(f"/api/threads/{tid}/resume", json={"decision": "approve"}).text
        )
        assert done[-1]["data"]["status"] == "dispatched"
        assert any(e["type"] == "answer" and "TASK-0001" in e["data"]["text"] for e in done)
        assert client.get("/api/ops/tasks").json()[0]["status"] == "dispatched"
        facts = client.get("/api/memory", params={"ward_id": "W-07"}).json()
        assert {f["kind"] for f in facts} == {"decision", "reservation"}
        assert client.get(f"/api/threads/{tid}").json()["status"] == "dispatched"


def test_resume_without_interrupt_returns_409() -> None:
    with make_client([AIMessage(content="hello")]) as client:
        assert (
            client.post("/api/threads/abc/resume", json={"decision": "approve"}).status_code == 409
        )


def test_resume_validates_decision() -> None:
    with make_client() as client:
        res = client.post("/api/threads/abc/resume", json={"decision": "maybe"})
        assert res.status_code == 422


def test_stream_emits_error_event_when_llm_fails() -> None:
    llm = FakeToolCallingModel(responses=[], error=RuntimeError("groq is down"))
    with make_client(llm=llm) as client:
        events = parse_sse(
            client.post("/api/threads/t1/messages", json={"content": "Ward 7 water"}).text
        )
        assert events[-1]["type"] == "error"
        assert "groq is down" in events[-1]["data"]["message"]


def test_missing_api_key_reports_error_but_ops_work() -> None:
    with make_client(llm=None) as client:
        assert client.get("/api/health").json()["llm_configured"] is False
        events = parse_sse(client.post("/api/threads/t1/messages", json={"content": "hi"}).text)
        assert events[-1]["type"] == "error" and "GROQ_API_KEY" in events[-1]["data"]["message"]
        assert client.get("/api/ops/teams").status_code == 200
        assert client.get("/api/threads/t1").json()["status"] == "new"


def test_knowledge_search() -> None:
    with make_client() as client:
        hits = client.get(
            "/api/knowledge/search", params={"q": "drinking water litres per person"}
        ).json()
        assert hits[0]["citation"] == "sop-water-supply.md#daily-allowance"


@pytest.mark.parametrize("payload", [{"content": ""}, {"content": "x", "max_steps": 0}])
def test_message_validation(payload) -> None:
    with make_client() as client:
        assert client.post("/api/threads/t1/messages", json=payload).status_code == 422
