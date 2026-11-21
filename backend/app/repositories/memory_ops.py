"""Thread-safe in-memory ``OpsRepository`` used by the offline test suite."""

import threading
from datetime import UTC, datetime

from app.db.seed.loader import SeedData, default_seed
from app.domain import (
    Depot,
    DispatchTask,
    ReliefPlan,
    ResourceType,
    Route,
    RouteStatus,
    StockLevel,
    TaskStatus,
    Team,
    TeamSkill,
    TeamStatus,
    Ward,
)
from app.repositories.errors import NotFoundError
from app.repositories.rules import check_dispatch


class InMemoryOpsRepository:
    def __init__(self, seed: SeedData | None = None) -> None:
        self._seed = seed or default_seed()
        self._lock = threading.RLock()
        self.reset()

    # --- reads ---------------------------------------------------------------------------
    def list_wards(self) -> list[Ward]:
        return [w.model_copy() for w in self._wards.values()]

    def get_ward(self, ward_id: str) -> Ward:
        try:
            return self._wards[ward_id].model_copy()
        except KeyError:
            raise NotFoundError(f"Unknown ward {ward_id}") from None

    def list_depots(self) -> list[Depot]:
        with self._lock:
            return [d.model_copy(deep=True) for d in self._depots.values()]

    def get_stock(self, resource: ResourceType, depot_id: str | None = None) -> list[StockLevel]:
        with self._lock:
            if depot_id is not None and depot_id not in self._depots:
                raise NotFoundError(f"Unknown depot {depot_id}")
            levels = []
            for depot in sorted(self._depots.values(), key=lambda d: d.id):
                if depot_id is not None and depot.id != depot_id:
                    continue
                item = depot.item(resource)
                if item is None:
                    continue
                levels.append(
                    StockLevel(
                        depot_id=depot.id,
                        depot_name=depot.name,
                        resource=resource,
                        unit=item.unit,
                        quantity=item.quantity,
                        reserved=item.reserved,
                        available=item.available,
                    )
                )
            return levels

    def list_routes(self, ward_id: str | None = None, route_id: str | None = None) -> list[Route]:
        with self._lock:
            return [
                r.model_copy()
                for r in self._routes.values()
                if (ward_id is None or r.ward_id == ward_id)
                and (route_id is None or r.id == route_id)
            ]

    def update_route_status(
        self, route_id: str, status: RouteStatus, note: str | None = None
    ) -> Route:
        with self._lock:
            route = self._routes.get(route_id)
            if route is None:
                raise NotFoundError(f"Unknown route {route_id}")
            route.status = status
            if note is not None:
                route.note = note
            return route.model_copy()

    def list_teams(
        self, skill: TeamSkill | None = None, status: TeamStatus | None = None
    ) -> list[Team]:
        with self._lock:
            return [
                t.model_copy(deep=True)
                for t in self._teams.values()
                if (skill is None or skill in t.skills) and (status is None or t.status is status)
            ]

    def list_tasks(self) -> list[DispatchTask]:
        with self._lock:
            return [t.model_copy(deep=True) for t in self._tasks]

    # --- writes --------------------------------------------------------------------------
    def dispatch(
        self, plan: ReliefPlan, note: str = "", thread_id: str | None = None
    ) -> DispatchTask:
        with self._lock:
            check_dispatch(
                plan,
                ward_exists=plan.ward_id in self._wards,
                team=self._teams.get(plan.team_id),
                routes=self._routes,
                stock={d.id: d.item(plan.resource) for d in self._depots.values()},
            )
            for alloc in plan.allocations:
                item = self._depots[alloc.depot_id].item(plan.resource)
                item.reserved += alloc.quantity
            self._teams[plan.team_id].status = TeamStatus.DEPLOYED
            return self._add_task(plan, TaskStatus.DISPATCHED, note, thread_id)

    def record_rejection(
        self, plan: ReliefPlan, note: str = "", thread_id: str | None = None
    ) -> DispatchTask:
        with self._lock:
            return self._add_task(plan, TaskStatus.REJECTED, note, thread_id)

    def reset(self) -> None:
        with self._lock:
            seed = self._seed.model_copy(deep=True)
            self._wards = {w.id: w for w in seed.wards}
            self._depots = {d.id: d for d in seed.depots}
            self._routes = {r.id: r for r in seed.routes}
            self._teams = {t.id: t for t in seed.teams}
            self._tasks: list[DispatchTask] = []

    def _add_task(
        self, plan: ReliefPlan, status: TaskStatus, note: str, thread_id: str | None
    ) -> DispatchTask:
        task = DispatchTask(
            id=f"TASK-{len(self._tasks) + 1:04d}",
            plan=plan,
            status=status,
            created_at=datetime.now(UTC),
            decision_note=note,
            thread_id=thread_id,
        )
        self._tasks.append(task)
        return task.model_copy(deep=True)
