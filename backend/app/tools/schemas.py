"""Argument schemas for the agent tools (shown to the LLM as JSON schema)."""

from pydantic import Field

from app.domain import ResourceType, TeamSkill, TeamStatus
from app.domain.base import DepotId, DomainModel, RouteId, WardId


class StockLookupArgs(DomainModel):
    resource: ResourceType = Field(description="Resource to look up")
    depot_id: DepotId | None = Field(
        default=None, description="Optional depot (DEP-A, DEP-B or DEP-C); omit for all depots"
    )


class RoadStatusArgs(DomainModel):
    ward_id: WardId | None = Field(
        default=None, description="Ward id such as W-07 (Ward 7). Returns every route to it"
    )
    route_id: RouteId | None = Field(default=None, description="A single route id such as RT-03")


class SituationReportArgs(DomainModel):
    ward_id: WardId = Field(description="Ward id such as W-07 (Ward 7)")
    resource: ResourceType = Field(description="Resource the ward needs")


class ListTeamsArgs(DomainModel):
    skill: TeamSkill | None = Field(default=None, description="Only teams with this skill")
    status: TeamStatus | None = Field(
        default=TeamStatus.AVAILABLE, description="Team status filter; defaults to available"
    )
