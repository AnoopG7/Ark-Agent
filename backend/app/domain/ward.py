from pydantic import PositiveInt

from app.domain.base import DomainModel, NonEmptyStr, WardId


class Ward(DomainModel):
    """An administrative ward that can raise relief requests."""

    id: WardId
    name: NonEmptyStr
    population: PositiveInt
    zone: NonEmptyStr
