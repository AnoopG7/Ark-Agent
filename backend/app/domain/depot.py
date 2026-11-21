from typing import Self

from pydantic import Field, NonNegativeInt, computed_field, model_validator

from app.domain.base import DepotId, DomainModel, NonEmptyStr
from app.domain.enums import RESOURCE_UNITS, ResourceType, Unit


class StockItem(DomainModel):
    """Quantity of one resource held at a depot. ``reserved`` is stock promised to dispatches."""

    resource: ResourceType
    quantity: NonNegativeInt
    reserved: NonNegativeInt = 0
    unit: Unit | None = Field(default=None, description="Defaults to the resource's canonical unit")

    @model_validator(mode="after")
    def _check(self) -> Self:
        expected = RESOURCE_UNITS[self.resource]
        if self.unit is None:
            object.__setattr__(self, "unit", expected)
        elif self.unit is not expected:
            raise ValueError(f"unit for {self.resource} must be {expected}, got {self.unit}")
        if self.reserved > self.quantity:
            raise ValueError("reserved cannot exceed quantity")
        return self

    @computed_field  # type: ignore[prop-decorator]
    @property
    def available(self) -> int:
        return self.quantity - self.reserved


class Depot(DomainModel):
    """A relief depot and its current stock."""

    id: DepotId
    name: NonEmptyStr
    zone: NonEmptyStr
    stock: list[StockItem]

    @model_validator(mode="after")
    def _unique_resources(self) -> Self:
        seen = [item.resource for item in self.stock]
        if len(seen) != len(set(seen)):
            raise ValueError("duplicate resource in depot stock")
        return self

    def item(self, resource: ResourceType) -> StockItem | None:
        return next((s for s in self.stock if s.resource is resource), None)


class StockLevel(DomainModel):
    """Read model: one resource's stock at one depot, as returned to the agent."""

    depot_id: DepotId
    depot_name: NonEmptyStr
    resource: ResourceType
    unit: Unit
    quantity: NonNegativeInt
    reserved: NonNegativeInt
    available: NonNegativeInt
