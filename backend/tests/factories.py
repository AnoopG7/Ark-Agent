"""Builders for domain objects used across tests."""

from app.domain import ReliefPlan


def make_plan(
    *,
    ward_id: str = "W-07",
    resource: str = "drinking_water",
    people: int = 300,
    quantity_required: int = 900,
    allocations: list[tuple[str, int, str]] | None = None,
    team_id: str = "TM-01",
    eta_minutes: int = 75,
    citations: list[str] | None = None,
) -> ReliefPlan:
    """Build a plan; ``allocations`` are ``(depot_id, quantity, route_id)`` tuples."""
    allocations = allocations or [("DEP-A", 800, "RT-01"), ("DEP-C", 100, "RT-05")]
    return ReliefPlan(
        ward_id=ward_id,
        resource=resource,
        people=people,
        quantity_required=quantity_required,
        allocations=[
            {"depot_id": d, "resource": resource, "quantity": q, "route_id": r}
            for d, q, r in allocations
        ],
        team_id=team_id,
        eta_minutes=eta_minutes,
        rationale="test plan",
        citations=citations or [],
    )
