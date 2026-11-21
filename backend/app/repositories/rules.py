"""Dispatch invariants shared by every repository implementation."""

from collections.abc import Mapping

from app.domain import ReliefPlan, Route, RouteStatus, StockItem, Team, TeamStatus
from app.repositories.errors import ConflictError, InsufficientStockError, NotFoundError


def check_dispatch(
    plan: ReliefPlan,
    *,
    ward_exists: bool,
    team: Team | None,
    routes: Mapping[str, Route],
    stock: Mapping[str, StockItem | None],
) -> None:
    """Raise the first violated invariant for ``plan``.

    ``routes`` maps route id → route and ``stock`` maps depot id → the plan resource's stock item
    (``None`` if the depot does not stock it). Missing keys mean the entity does not exist.
    """
    if not ward_exists:
        raise NotFoundError(f"Unknown ward {plan.ward_id}")
    if team is None:
        raise NotFoundError(f"Unknown team {plan.team_id}")
    if team.status is not TeamStatus.AVAILABLE:
        raise ConflictError(f"Team {team.id} is not available (status: {team.status})")
    for alloc in plan.allocations:
        route = routes.get(alloc.route_id)
        if route is None:
            raise NotFoundError(f"Unknown route {alloc.route_id}")
        if alloc.depot_id not in stock:
            raise NotFoundError(f"Unknown depot {alloc.depot_id}")
        if route.depot_id != alloc.depot_id or route.ward_id != plan.ward_id:
            raise ConflictError(
                f"Route {route.id} does not connect {alloc.depot_id} to {plan.ward_id}"
            )
        if route.status is RouteStatus.BLOCKED:
            raise ConflictError(f"Route {route.id} ({route.name}) is blocked")
        item = stock[alloc.depot_id]
        available = item.available if item else 0
        if alloc.quantity > available:
            raise InsufficientStockError(
                f"{alloc.depot_id} has only {available} {plan.resource} available, "
                f"{alloc.quantity} requested"
            )
