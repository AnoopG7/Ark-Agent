from pydantic import Field, PositiveInt

from app.domain.base import DomainModel, WardId
from app.domain.enums import Priority, ResourceType


class ReliefRequest(DomainModel):
    """A structured relief request, e.g. 'Ward 7 needs drinking water for 300 people by evening'."""

    ward_id: WardId
    resource: ResourceType
    people: PositiveInt = Field(le=100_000)
    quantity_needed: PositiveInt | None = Field(
        default=None, description="Explicit quantity if stated; otherwise derived from guidelines"
    )
    deadline_hours: float | None = Field(default=None, gt=0, le=72)
    priority: Priority = Priority.HIGH
