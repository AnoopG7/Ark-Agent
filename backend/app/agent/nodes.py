"""Graph nodes: load_memory -> reason <-> tools -> approval -> finalize_plan."""

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool
from langgraph.types import Command, interrupt
from pydantic import ValidationError

from app.agent.llm import invoke_with_retry
from app.agent.prompts import render_system_prompt
from app.agent.state import AgentState, ApprovalDecision
from app.agent.validator import validate_plan
from app.domain import DispatchTask, FactKind, MemoryFact, ReliefPlan, ToolResult
from app.memory.facts import FactsService
from app.repositories.errors import RepositoryError
from app.repositories.interfaces import OpsRepository
from app.tools.dispatch import DISPATCH_TOOL_NAME
from app.tools.executor import run_tool
from app.tools.guidelines import GUIDELINE_TOOL_NAME

_WARD_MENTION = re.compile(r"\bward\s*(\d{1,2})\b|\bW-(\d{2})\b", re.I)


def ward_ids_in(text: str) -> list[str]:
    ids = []
    for a, b in _WARD_MENTION.findall(text):
        ward = f"W-{int(a or b):02d}"
        if ward not in ids:
            ids.append(ward)
    return ids


def current_request_messages(messages: list) -> list:
    """Messages since (and including) the latest coordinator message."""
    for i in range(len(messages) - 1, -1, -1):
        if isinstance(messages[i], HumanMessage):
            return messages[i:]
    return messages


def retrieved_citations(messages: list) -> set[str]:
    """Citations returned by ``search_guidelines`` during the current request."""
    found: set[str] = set()
    for msg in current_request_messages(messages):
        if isinstance(msg, ToolMessage) and msg.name == GUIDELINE_TOOL_NAME:
            try:
                data = json.loads(msg.content)["data"] or {}
            except (ValueError, KeyError, TypeError):
                continue
            found.update(r["citation"] for r in data.get("results", []))
    return found


def _tool_message(call: dict, result: ToolResult) -> ToolMessage:
    return ToolMessage(
        content=result.model_dump_json(),
        tool_call_id=call["id"],
        name=call["name"],
        status="success" if result.ok else "error",
    )


def _thread_id(config: RunnableConfig) -> str | None:
    return (config.get("configurable") or {}).get("thread_id")


def describe_task(task: DispatchTask) -> str:
    p = task.plan
    legs = "; ".join(
        f"{a.quantity} {p.resource} from {a.depot_id} via {a.route_id}" for a in p.allocations
    )
    return (
        f"{task.id} dispatched to {p.ward_id} for {p.people} people: {legs}. Team {p.team_id}, "
        f"ETA {p.eta_minutes} min."
    )


@dataclass
class AgentNodes:
    llm: BaseChatModel
    tools: list[BaseTool]
    repo: OpsRepository
    facts: FactsService | None
    max_steps: int
    clock: Callable[[], datetime] = lambda: datetime.now(UTC)

    def __post_init__(self) -> None:
        self._tools_by_name = {t.name: t for t in self.tools}
        self._bound = self.llm.bind_tools(self.tools)

    def max_steps_for(self, config: RunnableConfig) -> int:
        return int((config.get("configurable") or {}).get("max_steps", self.max_steps))

    # ---- load_memory ---------------------------------------------------------------------
    def load_memory(self, state: AgentState) -> dict[str, Any]:
        """Start of every request: reset per-request counters and load relevant long-term facts."""
        context = ""
        if self.facts is not None:
            latest = current_request_messages(state["messages"])[0]
            wards = ward_ids_in(str(latest.content))
            facts: list[MemoryFact] = []
            for ward in wards:
                facts.extend(self.facts.list(ward_id=ward, limit=5))
            if not wards:
                facts = self.facts.list(limit=5)
            context = "\n".join(
                f"- [{f.created_at:%Y-%m-%d %H:%M}] ({f.kind}) {f.content}" for f in facts
            )
        return {
            "step_count": 0,
            "status": "running",
            "memory_context": context,
            "proposed_plan": None,
            "dispatched_task": None,
        }

    # ---- reason --------------------------------------------------------------------------
    def reason(self, state: AgentState, config: RunnableConfig) -> dict[str, Any]:
        """One ReAct step: the LLM thinks and either calls tools or answers."""
        system = SystemMessage(
            render_system_prompt(
                self.max_steps_for(config), state.get("memory_context", ""), self.clock()
            )
        )
        response = invoke_with_retry(self._bound, [system, *state["messages"]])
        return {"messages": [response], "step_count": state.get("step_count", 0) + 1}

    # ---- tools ---------------------------------------------------------------------------
    def run_tools(self, state: AgentState, config: RunnableConfig) -> dict[str, Any]:
        """Execute the read-only tool calls of the last reasoning step (observations)."""
        last: AIMessage = state["messages"][-1]
        return {"messages": [self._execute(call, config) for call in last.tool_calls]}

    def _execute(self, call: dict, config: RunnableConfig) -> ToolMessage:
        tool = self._tools_by_name.get(call["name"])
        if tool is None:
            return _tool_message(call, ToolResult.failure(f"Unknown tool {call['name']}"))
        return _tool_message(call, run_tool(tool, call["args"], config))

    # ---- approval ------------------------------------------------------------------------
    def approval(
        self, state: AgentState, config: RunnableConfig
    ) -> Command[Literal["reason", "finalize_plan"]]:
        """Human-in-the-loop checkpoint before any dispatch.

        Validates the proposed plan first; an invalid plan goes back to ``reason`` with the
        violations and never reaches the coordinator. ``interrupt()`` is called before any write,
        because LangGraph re-runs this node from the top when the run is resumed.
        """
        last: AIMessage = state["messages"][-1]
        dispatch_calls = [c for c in last.tool_calls if c["name"] == DISPATCH_TOOL_NAME]
        other_calls = [c for c in last.tool_calls if c["name"] != DISPATCH_TOOL_NAME]
        call, extra = dispatch_calls[0], dispatch_calls[1:]
        replies = [
            _tool_message(c, ToolResult.failure("Only one dispatch can be proposed at a time."))
            for c in extra
        ]

        def back_to_reason(result: ToolResult) -> Command:
            observed = [self._execute(c, config) for c in other_calls]
            return Command(
                goto="reason",
                update={"messages": [*observed, _tool_message(call, result), *replies]},
            )

        try:
            plan = ReliefPlan.model_validate(call["args"])
        except ValidationError as exc:
            errors = "; ".join(
                f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors()[:5]
            )
            return back_to_reason(ToolResult.failure(f"Invalid plan - {errors}"))

        violations = validate_plan(plan, self.repo, retrieved_citations(state["messages"]))
        if violations:
            return back_to_reason(
                ToolResult.failure("Plan rejected by validation: " + " ".join(violations))
            )

        raw = interrupt(
            {
                "type": "dispatch_approval",
                "plan": plan.model_dump(mode="json"),
                "message": "Approve this dispatch? Stock will be reserved and the team deployed.",
            }
        )
        try:
            decision = ApprovalDecision.model_validate(raw)
        except ValidationError as exc:
            return back_to_reason(ToolResult.failure(f"Invalid approval response: {exc}"))

        thread = _thread_id(config)
        observed = [self._execute(c, config) for c in other_calls]
        if decision.decision == "approve":
            try:
                task = self.repo.dispatch(plan, note=decision.note, thread_id=thread)
            except RepositoryError as exc:
                return back_to_reason(ToolResult.failure(f"Dispatch failed: {exc}"))
            self._remember_dispatch(task, thread)
            result = ToolResult.success({"task": task.model_dump(mode="json")})
            return Command(
                goto="finalize_plan",
                update={
                    "messages": [*observed, _tool_message(call, result), *replies],
                    "status": "dispatched",
                    "proposed_plan": plan.model_dump(mode="json"),
                    "dispatched_task": task.model_dump(mode="json"),
                },
            )

        task = self.repo.record_rejection(plan, note=decision.note, thread_id=thread)
        self._remember(
            FactKind.REJECTION,
            f"Plan for {plan.ward_id} ({plan.resource}, team {plan.team_id}) was "
            f"{'sent back for revision' if decision.decision == 'revise' else 'rejected'}: "
            f"{decision.note or 'no reason given'}.",
            plan.ward_id,
            thread,
        )
        if decision.decision == "revise":
            feedback = ToolResult.failure(
                f"Coordinator asked for a revised plan ({task.id}): {decision.note}"
            )
            return Command(
                goto="reason",
                update={"messages": [*observed, _tool_message(call, feedback), *replies]},
            )
        result = ToolResult.failure(
            f"Coordinator rejected the plan ({task.id}): {decision.note or 'no reason given'}"
        )
        return Command(
            goto="finalize_plan",
            update={
                "messages": [*observed, _tool_message(call, result), *replies],
                "status": "rejected",
                "proposed_plan": plan.model_dump(mode="json"),
            },
        )

    def _remember(self, kind: FactKind, content: str, ward: str | None, thread: str | None) -> None:
        if self.facts is not None:
            self.facts.save(
                MemoryFact(kind=kind, content=content[:500], ward_id=ward, source_thread=thread)
            )

    def _remember_dispatch(self, task: DispatchTask, thread: str | None) -> None:
        p = task.plan
        self._remember(FactKind.DECISION, describe_task(task), p.ward_id, thread)
        for a in p.allocations:
            self._remember(
                FactKind.RESERVATION,
                f"{a.depot_id} reserved {a.quantity} {p.resource} for {p.ward_id} ({task.id}).",
                p.ward_id,
                thread,
            )

    # ---- finalize_plan -------------------------------------------------------------------
    def finalize_plan(self, state: AgentState, config: RunnableConfig) -> dict[str, Any]:
        """Close the request with a definite outcome and a valid message history."""
        messages = state["messages"]
        last = messages[-1]
        status = state.get("status", "running")

        if isinstance(last, AIMessage) and last.tool_calls:
            limit = self.max_steps_for(config)
            skipped = [
                _tool_message(
                    c, ToolResult.failure(f"Not executed: step limit of {limit} reached.")
                )
                for c in last.tool_calls
            ]
            summary = AIMessage(
                content=(
                    f"I reached the step limit ({limit} steps) before completing a plan, so "
                    "nothing has been dispatched. Please narrow the request or confirm the "
                    "details (ward, resource, number of people) and ask again."
                )
            )
            return {"messages": [*skipped, summary], "status": "step_limit"}

        if status == "dispatched":
            task = DispatchTask.model_validate(state["dispatched_task"])
            text = f"Approved and dispatched. {describe_task(task)}"
            if task.plan.shortfall:
                text += f" Shortfall: {task.plan.shortfall} {task.plan.resource} still needed."
            return {"messages": [AIMessage(content=text)]}

        if status == "rejected":
            return {
                "messages": [
                    AIMessage(content="Understood - the plan was rejected and nothing was sent.")
                ]
            }

        return {"status": "answered"}
