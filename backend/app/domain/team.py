from pydantic import Field, PositiveInt

from app.domain.base import DepotId, DomainModel, NonEmptyStr, TeamId
from app.domain.enums import TeamSkill, TeamStatus, VehicleType


class Team(DomainModel):
    """A volunteer team that can be dispatched with supplies."""

    id: TeamId
    name: NonEmptyStr
    skills: list[TeamSkill] = Field(min_length=1)
    size: PositiveInt = Field(le=50)
    status: TeamStatus
    base_depot: DepotId
    vehicle: VehicleType
