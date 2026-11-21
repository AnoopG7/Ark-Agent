"""Operational data for the dashboard: wards, depots, routes, teams and dispatch tasks."""

from fastapi import APIRouter, HTTPException, status

from app.api.deps import Container
from app.api.schemas import RouteUpdate
from app.domain import Depot, DispatchTask, Route, Team, Ward
from app.repositories.errors import NotFoundError

router = APIRouter(prefix="/ops", tags=["operations"])


@router.get("/wards", response_model=list[Ward])
def wards(c: Container) -> list[Ward]:
    return c.repo.list_wards()


@router.get("/depots", response_model=list[Depot])
def depots(c: Container) -> list[Depot]:
    return c.repo.list_depots()


@router.get("/routes", response_model=list[Route])
def routes(c: Container, ward_id: str | None = None) -> list[Route]:
    return c.repo.list_routes(ward_id=ward_id)


@router.patch("/routes/{route_id}", response_model=Route)
def update_route(route_id: str, body: RouteUpdate, c: Container) -> Route:
    try:
        return c.repo.update_route_status(route_id, body.status, body.note)
    except NotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc


@router.get("/teams", response_model=list[Team])
def teams(c: Container) -> list[Team]:
    return c.repo.list_teams()


@router.get("/tasks", response_model=list[DispatchTask])
def tasks(c: Container) -> list[DispatchTask]:
    return list(reversed(c.repo.list_tasks()))


@router.post("/reset", status_code=status.HTTP_204_NO_CONTENT)
def reset(c: Container) -> None:
    c.repo.reset()
