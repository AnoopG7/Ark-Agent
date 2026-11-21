from pydantic import Field, PositiveInt

from app.domain.base import DepotId, DomainModel, NonEmptyStr, RouteId, WardId
from app.domain.enums import RouteStatus, VehicleType


class Route(DomainModel):
    """A road or waterway connecting a depot to a ward."""

    id: RouteId
    name: NonEmptyStr
    depot_id: DepotId
    ward_id: WardId
    status: RouteStatus
    travel_minutes: PositiveInt = Field(le=24 * 60)
    vehicle: VehicleType = Field(description="Vehicle type the route can carry")
    note: str = Field(default="", max_length=300)
