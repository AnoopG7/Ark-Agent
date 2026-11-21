"""Shared helpers for the demo scripts (real Postgres + Groq, same wiring as the API)."""

from uuid import uuid4

from langchain_core.messages import HumanMessage
from langgraph.types import Command

from app.api.container import AppContainer
from app.api.streaming import stream_run
from app.evaluation.report import _short


def run_and_print(c: AppContainer, graph_input, config: dict) -> None:
    for e in stream_run(c.graph, graph_input, config):
        d = e.data
        if e.type == "thought":
            print(f"  [{e.step}] Thought: {_short(d['text'], 200)}")
        elif e.type == "tool_call":
            print(f"  [{e.step}] Act:     {d['name']} {_short(d['args'], 120)}")
        elif e.type == "tool_result":
            body = d.get("data") if d.get("ok") else d.get("error")
            print(f"           Observe: {'ok' if d.get('ok') else 'ERROR'} {_short(body, 140)}")
        elif e.type == "interrupt":
            p = d["plan"]
            legs = ", ".join(
                f"{a['quantity']} from {a['depot_id']} via {a['route_id']}"
                for a in p["allocations"]
            )
            print(
                f"  PAUSED for approval: {p['ward_id']} {p['resource']}: {legs}; "
                f"team {p['team_id']}"
            )
        elif e.type == "answer":
            print(f"  Answer: {d['text']}")
        elif e.type == "done":
            print(f"  -> status: {d['status']} after {d['step_count']} steps")
        elif e.type == "error":
            print(f"  ERROR: {d['message']}")


def ask(c: AppContainer, thread_id: str, text: str) -> None:
    print(f"\nCoordinator: {text}")
    run_and_print(c, {"messages": [HumanMessage(text)]}, {"configurable": {"thread_id": thread_id}})


def decide(c: AppContainer, thread_id: str, decision: str, note: str = "") -> None:
    print(f"\nCoordinator decision: {decision.upper()} {note}")
    run_and_print(
        c,
        Command(resume={"decision": decision, "note": note}),
        {"configurable": {"thread_id": thread_id}},
    )


def new_thread(label: str) -> str:
    return f"{label}-{uuid4().hex[:8]}"
