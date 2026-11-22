"""Translate LangGraph stream updates into typed ``AgentEvent``s and SSE frames."""

import json
import logging
from collections.abc import Iterator
from typing import Any

from langchain_core.messages import AIMessage, ToolMessage
from langgraph.graph.state import CompiledStateGraph

from app.api.schemas import AgentEvent

log = logging.getLogger(__name__)


def sse(event: AgentEvent) -> str:
    return f"event: {event.type}\ndata: {event.model_dump_json()}\n\n"


def _tool_result(msg: ToolMessage, step: int) -> AgentEvent:
    try:
        payload = json.loads(msg.content)
    except (TypeError, ValueError):
        payload = {"ok": msg.status != "error", "data": msg.content, "error": None}
    return AgentEvent(
        type="tool_result",
        step=step,
        data={"tool_call_id": msg.tool_call_id, "name": msg.name, **payload},
    )


def events_from_update(node: str, update: Any, step: int) -> list[AgentEvent]:
    if node == "__interrupt__":
        return [
            AgentEvent(type="interrupt", step=step, data={"id": i.id, **i.value}) for i in update
        ]
    if not isinstance(update, dict):
        return []
    events: list[AgentEvent] = []
    for msg in update.get("messages", []):
        if isinstance(msg, AIMessage):
            text = msg.text if isinstance(msg.text, str) else str(msg.content)
            if msg.tool_calls:
                # Reasoning models (e.g. gpt-oss on Groq) leave ``content`` empty on tool-call
                # turns and return their thinking separately; surface it as the step's thought.
                if not text.strip():
                    text = str(msg.additional_kwargs.get("reasoning_content") or "")
                if text.strip():
                    events.append(AgentEvent(type="thought", step=step, data={"text": text}))
                events.extend(
                    AgentEvent(
                        type="tool_call",
                        step=step,
                        data={"id": c["id"], "name": c["name"], "args": c["args"]},
                    )
                    for c in msg.tool_calls
                )
            elif node in ("reason", "finalize_plan") and text.strip():
                events.append(AgentEvent(type="answer", step=step, data={"text": text}))
        elif isinstance(msg, ToolMessage):
            events.append(_tool_result(msg, step))
    return events


def stream_run(
    graph: CompiledStateGraph, graph_input: Any, config: dict[str, Any]
) -> Iterator[AgentEvent]:
    """Run the graph and yield events; always ends with ``done`` or ``error``."""
    step = 0
    try:
        for chunk in graph.stream(graph_input, config, stream_mode="updates"):
            for node, update in chunk.items():
                if node == "reason" and isinstance(update, dict):
                    step = update.get("step_count", step)
                yield from events_from_update(node, update, step)
        snapshot = graph.get_state(config)
        status = "awaiting_approval" if snapshot.interrupts else snapshot.values.get("status")
        yield AgentEvent(
            type="done",
            step=step,
            data={"status": status, "step_count": snapshot.values.get("step_count", 0)},
        )
    except Exception as exc:  # noqa: BLE001 - reported to the client as an event
        log.exception("agent run failed")
        yield AgentEvent(type="error", step=step, data={"message": f"{type(exc).__name__}: {exc}"})
