from typing import Self

from pydantic import Field, NonNegativeInt, PositiveInt, computed_field, model_validator

from app.domain.base import Citation, DepotId, DomainModel, RouteId, TeamId, WardId
from app.domain.enums import ResourceType


class Allocation(DomainModel):
    """Quantity taken from one depot, delivered over one route."""

    depot_id: DepotId
    resource: ResourceType
    quantity: PositiveInt
    route_id: RouteId


class ReliefPlan(DomainModel):
    """A proposed fulfilment of a relief request. This is the payload a coordinator approves."""

    ward_id: WardId
    resource: ResourceType
    people: PositiveInt
    quantity_required: PositiveInt
    allocations: list[Allocation] = Field(min_length=1, max_length=3)
    team_id: TeamId
    eta_minutes: PositiveInt = Field(le=24 * 60)
    rationale: str = Field(min_length=1, max_length=1000)
    citations: list[Citation] = Field(default_factory=list, max_length=6)

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if any(a.resource is not self.resource for a in self.allocations):
            raise ValueError("every allocation resource must match the plan resource")
        depots = [a.depot_id for a in self.allocations]
        if len(depots) != len(set(depots)):
            raise ValueError("at most one allocation per depot")
        return self

    @computed_field  # type: ignore[prop-decorator]
    @property
    def total_allocated(self) -> int:
        return sum(a.quantity for a in self.allocations)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def shortfall(self) -> NonNegativeInt:
        return max(0, self.quantity_required - self.total_allocated)
