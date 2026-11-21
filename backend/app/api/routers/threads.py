"""Conversation threads: send requests to the agent and answer approval checkpoints."""

import json
from collections.abc import Iterator
from uuid import uuid4

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.types import Command

from app.api.container import AppContainer
from app.api.deps import Container
from app.api.schemas import (
    AgentEvent,
    ChatMessage,
    ResumeRequest,
    SendMessageRequest,
    ThreadCreated,
    ThreadState,
)
from app.api.streaming import sse, stream_run

router = APIRouter(prefix="/threads", tags=["threads"])


def _config(thread_id: str, max_steps: int | None = None) -> dict:
    configurable: dict = {"thread_id": thread_id}
    if max_steps is not None:
        configurable["max_steps"] = max_steps
    return {"configurable": configurable}


def _sse_response(c: AppContainer, thread_id: str, graph_input, config: dict) -> StreamingResponse:
    lock = c.thread_lock(thread_id)
    if not lock.acquire(blocking=False):
        raise HTTPException(status.HTTP_409_CONFLICT, "This thread is already running.")

    def body() -> Iterator[str]:
        try:
            yield sse(AgentEvent(type="run_started", data={"thread_id": thread_id}))
            try:
                graph = c.graph
            except Exception as exc:  # noqa: BLE001 - e.g. missing GROQ_API_KEY
                yield sse(AgentEvent(type="error", data={"message": str(exc)}))
                return
            for event in stream_run(graph, graph_input, config):
                yield sse(event)
        finally:
            lock.release()

    return StreamingResponse(
        body(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _pending_interrupt(c: AppContainer, thread_id: str):
    try:
        snapshot = c.graph.get_state(_config(thread_id))
    except Exception:  # noqa: BLE001 - no graph (LLM not configured) means nothing is pending
        return None, None
    return snapshot, (snapshot.interrupts[0] if snapshot.interrupts else None)


@router.post("", response_model=ThreadCreated, status_code=status.HTTP_201_CREATED)
def create_thread() -> ThreadCreated:
    return ThreadCreated(thread_id=uuid4().hex)


@router.post("/{thread_id}/messages")
def send_message(thread_id: str, body: SendMessageRequest, c: Container) -> StreamingResponse:
    _, pending = _pending_interrupt(c, thread_id)
    if pending is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "A dispatch is awaiting approval on this thread."
        )
    return _sse_response(
        c,
        thread_id,
        {"messages": [HumanMessage(body.content)]},
        _config(thread_id, body.max_steps),
    )


@router.post("/{thread_id}/resume")
def resume(thread_id: str, body: ResumeRequest, c: Container) -> StreamingResponse:
    _, pending = _pending_interrupt(c, thread_id)
    if pending is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Nothing is awaiting approval.")
    return _sse_response(c, thread_id, Command(resume=body.model_dump()), _config(thread_id))


def _to_chat(msg) -> ChatMessage | None:
    if isinstance(msg, HumanMessage):
        return ChatMessage(role="user", content=str(msg.content))
    if isinstance(msg, AIMessage):
        return ChatMessage(
            role="assistant",
            content=msg.text if isinstance(msg.text, str) else str(msg.content),
            tool_calls=[
                {"id": t["id"], "name": t["name"], "args": t["args"]} for t in msg.tool_calls
            ],
        )
    if isinstance(msg, ToolMessage):
        try:
            ok = bool(json.loads(msg.content).get("ok"))
        except (TypeError, ValueError, AttributeError):
            ok = msg.status != "error"
        return ChatMessage(
            role="tool",
            content=str(msg.content),
            name=msg.name,
            tool_call_id=msg.tool_call_id,
            ok=ok,
        )
    return None


@router.get("/{thread_id}", response_model=ThreadState)
def get_thread(thread_id: str, c: Container) -> ThreadState:
    snapshot, pending = _pending_interrupt(c, thread_id)
    values = snapshot.values if snapshot else {}
    messages = [m for m in (_to_chat(x) for x in values.get("messages", [])) if m]
    if pending is not None:
        state = "awaiting_approval"
    else:
        state = values.get("status", "new") if messages else "new"
    return ThreadState(
        thread_id=thread_id,
        status=state,
        step_count=values.get("step_count", 0),
        messages=messages,
        pending_approval={"id": pending.id, **pending.value} if pending else None,
    )
