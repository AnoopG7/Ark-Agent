"""Graph state and the coordinator's approval decision schema."""

from typing import Annotated, Any, Literal, Self, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages
from pydantic import Field, model_validator

from app.domain.base import DomainModel

RunStatus = Literal["running", "answered", "dispatched", "rejected", "step_limit"]


class AgentState(TypedDict, total=False):
    """State carried through the graph and checkpointed per thread (short-term memory)."""

    messages: Annotated[list[AnyMessage], add_messages]
    step_count: int
    """Reasoning steps (LLM calls) used for the current request; reset on each new request."""
    status: RunStatus
    memory_context: str
    """Long-term facts loaded for the wards mentioned in the current request."""
    proposed_plan: dict[str, Any] | None
    dispatched_task: dict[str, Any] | None


class ApprovalDecision(DomainModel):
    """What the coordinator sends to resume a run paused at the approval checkpoint."""

    decision: Literal["approve", "reject", "revise"]
    note: str = Field(default="", max_length=500)

    @model_validator(mode="after")
    def _revise_needs_note(self) -> Self:
        if self.decision == "revise" and not self.note.strip():
            raise ValueError("a revise decision must explain what to change")
        return self
