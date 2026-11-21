"""Run scenarios against the real agent (Groq + local embeddings) and record full traces."""

import json
import time
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.memory import InMemoryStore
from langgraph.types import Command

from app.agent.graph import build_graph
from app.agent.validator import validate_plan
from app.api.streaming import events_from_update
from app.domain import DispatchTask, ReliefPlan
from app.evaluation.metrics import ToolCallRecord, tool_histogram, unnecessary_calls
from app.evaluation.scenarios import Scenario
from app.rag.retriever import Retriever
from app.repositories.memory_ops import InMemoryOpsRepository


@dataclass
class RunRecord:
    scenario: Scenario
    events: list[dict[str, Any]] = field(default_factory=list)
    calls: list[ToolCallRecord] = field(default_factory=list)
    tasks: list[DispatchTask] = field(default_factory=list)
    final_status: str = ""
    final_text: str = ""
    steps_total: int = 0
    steps_per_request: list[int] = field(default_factory=list)
    proposals: int = 0
    invalid_proposals: list[str] = field(default_factory=list)
    approvals_given: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    latency_s: float = 0.0
    retrieved_citations: set[str] = field(default_factory=set)
    deviations: list[str] = field(default_factory=list)
    error: str | None = None
    check_results: dict[str, bool] = field(default_factory=dict)

    # ---- derived metrics ---------------------------------------------------------------
    @property
    def unnecessary(self) -> list[ToolCallRecord]:
        return unnecessary_calls(self.calls, self.scenario.resources)

    @property
    def histogram(self) -> dict[str, int]:
        return tool_histogram(self.calls)

    @property
    def dispatched(self) -> list[DispatchTask]:
        return [t for t in self.tasks if t.status == "dispatched"]

    @property
    def approval_respected(self) -> bool:
        return len(self.dispatched) <= self.approvals_given

    @property
    def passed(self) -> bool:
        return self.error is None and all(self.check_results.values())


class ScenarioRunner:
    """Runs one scenario on a fresh in-memory operation state with the real LLM and RAG."""

    def __init__(self, llm, retriever: Retriever, default_max_steps: int = 8) -> None:
        self.llm = llm
        self.retriever = retriever
        self.default_max_steps = default_max_steps

    def run(self, scenario: Scenario) -> RunRecord:
        record = RunRecord(scenario=scenario)
        repo = InMemoryOpsRepository()
        store = InMemoryStore()
        max_steps = scenario.max_steps or self.default_max_steps

        def new_graph():
            return build_graph(
                llm=self.llm,
                repo=repo,
                checkpointer=InMemorySaver(),  # short-term memory is per shift
                store=store,  # long-term memory survives across shifts
                retriever=self.retriever,
                max_steps=max_steps,
            )

        graph = new_graph()
        config = {"configurable": {"thread_id": uuid4().hex, "max_steps": max_steps}}
        started = time.perf_counter()
        try:
            for index, turn in enumerate(scenario.turns):
                if turn.kind == "new_shift":
                    graph = new_graph()
                    config = {"configurable": {"thread_id": uuid4().hex, "max_steps": max_steps}}
                    record.events.append({"turn": index, "type": "new_shift", "data": {}})
                    continue
                pending = graph.get_state(config).interrupts
                if turn.kind == "message":
                    if pending:
                        record.deviations.append(
                            f"turn {index}: message sent while approval pending"
                        )
                        continue
                    graph_input: Any = {"messages": [HumanMessage(turn.text)]}
                else:
                    if not pending:
                        record.deviations.append(
                            f"turn {index}: expected an approval checkpoint for '{turn.kind}', "
                            "but the agent did not propose a dispatch"
                        )
                        continue
                    if turn.kind == "approve":
                        record.approvals_given += 1
                    graph_input = Command(resume={"decision": turn.kind, "note": turn.text})
                record.events.append(
                    {"turn": index, "type": f"coordinator_{turn.kind}", "data": {"text": turn.text}}
                )
                self._stream(graph, graph_input, config, index, record)
                values = graph.get_state(config).values
                record.final_status = (
                    "awaiting_approval"
                    if graph.get_state(config).interrupts
                    else values.get("status", "")
                )
                if turn.kind == "message" or record.final_status != "running":
                    record.steps_per_request.append(values.get("step_count", 0))
        except Exception as exc:  # noqa: BLE001 - recorded, not raised, so other scenarios run
            record.error = f"{type(exc).__name__}: {exc}"
        record.latency_s = round(time.perf_counter() - started, 2)
        record.tasks = repo.list_tasks()
        for name, check in scenario.checks.items():
            try:
                record.check_results[name] = bool(check(record))
            except Exception:  # noqa: BLE001
                record.check_results[name] = False
        return record

    def _stream(self, graph, graph_input, config, turn: int, record: RunRecord) -> None:
        by_id: dict[str, ToolCallRecord] = {}
        for chunk in graph.stream(graph_input, config, stream_mode="updates"):
            for node, update in chunk.items():
                if node == "reason" and isinstance(update, dict):
                    record.steps_total += 1
                    for msg in update.get("messages", []):
                        if isinstance(msg, AIMessage) and msg.usage_metadata:
                            record.tokens_in += msg.usage_metadata.get("input_tokens", 0)
                            record.tokens_out += msg.usage_metadata.get("output_tokens", 0)
                step = record.steps_total
                for event in events_from_update(node, update, step):
                    record.events.append({"turn": turn, "node": node, **event.model_dump()})
                    data = event.data
                    if event.type == "tool_call":
                        call = ToolCallRecord(turn, step, data["name"], data["args"])
                        by_id[data["id"]] = call
                        record.calls.append(call)
                        if data["name"] == "create_dispatch_task":
                            record.proposals += 1
                    elif event.type == "tool_result":
                        call = by_id.get(data["tool_call_id"])
                        if call:
                            call.ok, call.error = data.get("ok"), data.get("error")
                        if data["name"] == "create_dispatch_task" and not data.get("ok"):
                            err = data.get("error") or ""
                            if err.startswith(("Plan rejected by validation", "Invalid plan")):
                                record.invalid_proposals.append(err)
                        if data["name"] == "search_guidelines" and data.get("ok"):
                            for hit in (data.get("data") or {}).get("results", []):
                                record.retrieved_citations.add(hit["citation"])
                    elif event.type == "answer":
                        record.final_text = data["text"]


def revalidate(task: DispatchTask) -> list[str]:
    """Check a dispatched plan against the *initial* seed state (independent of the agent)."""
    plan = ReliefPlan.model_validate(task.plan.model_dump())
    return validate_plan(plan, InMemoryOpsRepository(), plan.citations)


def to_json(record: RunRecord) -> dict[str, Any]:
    return {
        "scenario": {
            "id": record.scenario.id,
            "title": record.scenario.title,
            "purpose": record.scenario.purpose,
            "turns": [{"kind": t.kind, "text": t.text} for t in record.scenario.turns],
            "max_steps": record.scenario.max_steps,
        },
        "outcome": {
            "final_status": record.final_status,
            "final_text": record.final_text,
            "passed": record.passed,
            "checks": record.check_results,
            "deviations": record.deviations,
            "error": record.error,
        },
        "metrics": {
            "steps_total": record.steps_total,
            "steps_per_request": record.steps_per_request,
            "tool_calls": len(record.calls),
            "tool_histogram": record.histogram,
            "unnecessary_tool_calls": [
                {"step": c.step, "name": c.name, "args": c.args} for c in record.unnecessary
            ],
            "dispatch_proposals": record.proposals,
            "invalid_proposals": record.invalid_proposals,
            "approval_respected": record.approval_respected,
            "dispatched_plans_valid_against_seed": [revalidate(t) == [] for t in record.dispatched],
            "tokens_in": record.tokens_in,
            "tokens_out": record.tokens_out,
            "latency_s": record.latency_s,
        },
        "tasks": [t.model_dump(mode="json") for t in record.tasks],
        "trace": record.events,
    }


def dumps(record: RunRecord) -> str:
    return json.dumps(to_json(record), indent=2, ensure_ascii=False, default=str)
