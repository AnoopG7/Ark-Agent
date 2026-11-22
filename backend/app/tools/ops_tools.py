"""Read-only tools over operational data: stock, roads and teams."""

from langchain_core.tools import BaseTool, StructuredTool

from app.agent.policy import REQUIRED_SKILL
from app.domain import ResourceType, RouteStatus, TeamSkill, TeamStatus, ToolResult
from app.tools.context import ToolContext
from app.tools.schemas import (
    ListTeamsArgs,
    RoadStatusArgs,
    SituationReportArgs,
    StockLookupArgs,
)


def build_ops_tools(ctx: ToolContext) -> list[BaseTool]:
    repo = ctx.repo

    def stock_lookup(resource: ResourceType, depot_id: str | None = None) -> ToolResult:
        levels = repo.get_stock(resource, depot_id)
        return ToolResult.success(
            {
                "resource": resource,
                "unit": levels[0].unit if levels else None,
                "depots": [lvl.model_dump(mode="json") for lvl in levels],
                "total_available": sum(lvl.available for lvl in levels),
            }
        )

    def road_status(ward_id: str | None = None, route_id: str | None = None) -> ToolResult:
        if ward_id is not None:
            repo.get_ward(ward_id)  # raises NotFoundError for unknown wards
        routes = repo.list_routes(ward_id=ward_id, route_id=route_id)
        return ToolResult.success(
            {
                "routes": [
                    {**r.model_dump(mode="json"), "usable": r.status is not RouteStatus.BLOCKED}
                    for r in sorted(routes, key=lambda r: r.travel_minutes)
                ],
                "message": None if routes else "No route reaches this ward from any depot.",
            }
        )

    def list_teams(
        skill: TeamSkill | None = None, status: TeamStatus | None = TeamStatus.AVAILABLE
    ) -> ToolResult:
        teams = repo.list_teams(skill=skill, status=status)
        return ToolResult.success({"teams": [t.model_dump(mode="json") for t in teams]})

    def situation_report(ward_id: str, resource: ResourceType) -> ToolResult:
        """Everything needed to plan one request, in one compact observation."""
        ward = repo.get_ward(ward_id)
        levels = repo.get_stock(resource)
        routes = sorted(repo.list_routes(ward_id=ward_id), key=lambda r: r.travel_minutes)
        required = REQUIRED_SKILL.get(resource)
        teams = repo.list_teams(skill=required, status=TeamStatus.AVAILABLE)
        return ToolResult.success(
            {
                "ward": {"id": ward.id, "name": ward.name, "population": ward.population},
                "resource": resource,
                "unit": levels[0].unit if levels else None,
                "stock": [{"depot_id": lvl.depot_id, "available": lvl.available} for lvl in levels],
                "total_available": sum(lvl.available for lvl in levels),
                "routes": [
                    {
                        "id": r.id,
                        "depot_id": r.depot_id,
                        "status": r.status,
                        "travel_minutes": r.travel_minutes,
                        "vehicle": r.vehicle,
                        "usable": r.status is not RouteStatus.BLOCKED,
                    }
                    for r in routes
                ],
                "required_skill": required,
                "available_teams": [
                    {"id": t.id, "skills": t.skills, "vehicle": t.vehicle} for t in teams
                ],
                "message": None if routes else "No route reaches this ward from any depot.",
            }
        )

    return [
        StructuredTool.from_function(
            situation_report,
            name="situation_report",
            description=(
                "One-call overview for planning a request: available stock of the resource per "
                "depot, every route to the ward (status, time, vehicle, usable) and the available "
                "teams that can deliver it. Use this first instead of the three separate lookups."
            ),
            args_schema=SituationReportArgs,
        ),
        StructuredTool.from_function(
            stock_lookup,
            name="stock_lookup",
            description=(
                "Current stock of one resource at all depots (or one depot). Returns quantity, "
                "reserved and available per depot plus the total available."
            ),
            args_schema=StockLookupArgs,
        ),
        StructuredTool.from_function(
            road_status,
            name="road_status",
            description=(
                "Routes from depots to a ward with status (open, slow, blocked), travel time and "
                "vehicle type (truck or boat). Blocked routes cannot be used."
            ),
            args_schema=RoadStatusArgs,
        ),
        StructuredTool.from_function(
            list_teams,
            name="list_teams",
            description=(
                "Volunteer teams with skills, size, base depot and vehicle. Filters by skill and "
                "status (default: available)."
            ),
            args_schema=ListTeamsArgs,
        ),
    ]
