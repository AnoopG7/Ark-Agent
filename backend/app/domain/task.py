from pydantic import AwareDatetime, Field

from app.domain.base import DomainModel, TaskId
from app.domain.enums import TaskStatus
from app.domain.plan import ReliefPlan


class DispatchTask(DomainModel):
    """A coordinator decision on a relief plan. Dispatched tasks hold stock reservations."""

    id: TaskId
    plan: ReliefPlan
    status: TaskStatus
    created_at: AwareDatetime
    decision_note: str = Field(default="", max_length=500)
    thread_id: str | None = None
