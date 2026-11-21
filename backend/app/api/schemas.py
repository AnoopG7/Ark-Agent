"""Request and response bodies of the HTTP API."""

from typing import Any, Literal

from pydantic import Field

from app.agent.state import RunStatus
from app.domain import RouteStatus
from app.domain.base import DomainModel

EventType = Literal[
    "run_started", "thought", "tool_call", "tool_result", "interrupt", "answer", "done", "error"
]


class AgentEvent(DomainModel):
    """One Server-Sent Event emitted while the agent runs."""

    type: EventType
    step: int = 0
    data: dict[str, Any] = Field(default_factory=dict)


class HealthResponse(DomainModel):
    status: Literal["ok", "degraded"]
    database: bool
    llm_configured: bool
    model: str


class ThreadCreated(DomainModel):
    thread_id: str


class SendMessageRequest(DomainModel):
    content: str = Field(min_length=1, max_length=2000)
    max_steps: int | None = Field(default=None, ge=1, le=25)


class ResumeRequest(DomainModel):
    decision: Literal["approve", "reject", "revise"]
    note: str = Field(default="", max_length=500)


class ChatMessage(DomainModel):
    role: Literal["user", "assistant", "tool"]
    content: str
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    name: str | None = None
    tool_call_id: str | None = None
    ok: bool | None = None


class ThreadState(DomainModel):
    thread_id: str
    status: RunStatus | Literal["new", "awaiting_approval"]
    step_count: int
    messages: list[ChatMessage]
    pending_approval: dict[str, Any] | None = None


class RouteUpdate(DomainModel):
    status: RouteStatus
    note: str | None = Field(default=None, max_length=300)


class KnowledgeHit(DomainModel):
    citation: str
    title: str
    text: str
    score: float
