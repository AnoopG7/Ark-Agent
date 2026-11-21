"""Read-only tools over operational data: stock, roads and teams."""

from langchain_core.tools import BaseTool, StructuredTool

from app.domain import ResourceType, RouteStatus, TeamSkill, TeamStatus, ToolResult
from app.tools.context import ToolContext
from app.tools.schemas import ListTeamsArgs, RoadStatusArgs, StockLookupArgs


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

    return [
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
