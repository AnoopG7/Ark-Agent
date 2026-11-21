"""Storage-agnostic interfaces: Postgres implementations for the app, in-memory for tests."""

from typing import Protocol, runtime_checkable

from app.domain import (
    Depot,
    DispatchTask,
    ReliefPlan,
    ResourceType,
    Route,
    RouteStatus,
    StockLevel,
    Team,
    TeamSkill,
    TeamStatus,
    Ward,
)


@runtime_checkable
class OpsRepository(Protocol):
    """Read and update the operational state: wards, depots, stock, routes, teams and tasks."""

    def list_wards(self) -> list[Ward]: ...

    def get_ward(self, ward_id: str) -> Ward:
        """Raises ``NotFoundError`` if the ward does not exist."""
        ...

    def list_depots(self) -> list[Depot]: ...

    def get_stock(self, resource: ResourceType, depot_id: str | None = None) -> list[StockLevel]:
        """Stock of ``resource`` at every depot (or one depot), ordered by depot id."""
        ...

    def list_routes(
        self, ward_id: str | None = None, route_id: str | None = None
    ) -> list[Route]: ...

    def update_route_status(
        self, route_id: str, status: RouteStatus, note: str | None = None
    ) -> Route: ...

    def list_teams(
        self, skill: TeamSkill | None = None, status: TeamStatus | None = None
    ) -> list[Team]: ...

    def dispatch(
        self, plan: ReliefPlan, note: str = "", thread_id: str | None = None
    ) -> DispatchTask:
        """Atomically validate the plan against current state, reserve stock and deploy the team.

        Raises ``NotFoundError``, ``ConflictError`` or ``InsufficientStockError`` and leaves state
        unchanged if any allocation cannot be honoured.
        """
        ...

    def record_rejection(
        self, plan: ReliefPlan, note: str = "", thread_id: str | None = None
    ) -> DispatchTask:
        """Store a rejected plan for the audit trail. Reserves nothing."""
        ...

    def list_tasks(self) -> list[DispatchTask]: ...

    def reset(self) -> None:
        """Restore the initial seed state and clear all tasks."""
        ...
