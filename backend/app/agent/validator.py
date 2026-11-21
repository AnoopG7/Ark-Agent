"""Deterministic plan validation against live operational data and SOP rules.

Used by the approval node (an invalid plan never reaches the coordinator) and by the evaluation
harness (plan validity metric).
"""

from collections.abc import Iterable

from app.agent.policy import LOADING_MINUTES, REQUIRED_SKILL, minimum_quantity
from app.domain import ReliefPlan, RouteStatus, TeamSkill, TeamStatus, VehicleType
from app.repositories.errors import NotFoundError
from app.repositories.interfaces import OpsRepository


def validate_plan(
    plan: ReliefPlan, repo: OpsRepository, retrieved_citations: Iterable[str] = ()
) -> list[str]:
    """Return human-readable violations; an empty list means the plan is valid."""
    violations: list[str] = []
    try:
        repo.get_ward(plan.ward_id)
    except NotFoundError:
        return [f"Ward {plan.ward_id} does not exist."]

    minimum = minimum_quantity(plan.resource, plan.people)
    if minimum is not None and plan.quantity_required < minimum:
        violations.append(
            f"quantity_required {plan.quantity_required} is below the SOP minimum of {minimum} "
            f"{plan.resource} for {plan.people} people."
        )

    team = next((t for t in repo.list_teams(status=None) if t.id == plan.team_id), None)
    if team is None:
        violations.append(f"Team {plan.team_id} does not exist.")
    elif team.status is not TeamStatus.AVAILABLE:
        violations.append(f"Team {team.id} is {team.status}, not available.")
    required_skill = REQUIRED_SKILL.get(plan.resource)
    if team and required_skill and required_skill not in team.skills:
        violations.append(f"{plan.resource} must be delivered by a team with {required_skill}.")

    stock = {s.depot_id: s for s in repo.get_stock(plan.resource)}
    max_travel = 0
    for alloc in plan.allocations:
        routes = repo.list_routes(route_id=alloc.route_id)
        if not routes:
            violations.append(f"Route {alloc.route_id} does not exist.")
            continue
        route = routes[0]
        max_travel = max(max_travel, route.travel_minutes)
        if route.depot_id != alloc.depot_id or route.ward_id != plan.ward_id:
            violations.append(
                f"Route {route.id} runs {route.depot_id}->{route.ward_id}, "
                f"not {alloc.depot_id}->{plan.ward_id}."
            )
        if route.status is RouteStatus.BLOCKED:
            violations.append(f"Route {route.id} ({route.name}) is blocked.")
        if team and route.vehicle is VehicleType.BOAT:
            if team.vehicle is not VehicleType.BOAT or TeamSkill.BOAT_RESCUE not in team.skills:
                violations.append(
                    f"Route {route.id} is boat-only; team {team.id} has no boat crew."
                )
        elif team and team.vehicle is VehicleType.BOAT:
            violations.append(f"Team {team.id} travels by boat but route {route.id} is a road.")
        level = stock.get(alloc.depot_id)
        available = level.available if level else 0
        if alloc.quantity > available:
            violations.append(
                f"{alloc.depot_id} has only {available} {plan.resource} available "
                f"({alloc.quantity} allocated)."
            )

    if max_travel and plan.eta_minutes < max_travel:
        violations.append(
            f"eta_minutes {plan.eta_minutes} is shorter than the slowest route ({max_travel} min); "
            f"use {max_travel + LOADING_MINUTES} (travel + {LOADING_MINUTES} min loading)."
        )
    unknown = sorted(set(plan.citations) - set(retrieved_citations))
    if unknown:
        violations.append(f"Citations not retrieved in this request: {', '.join(unknown)}.")
    return violations
