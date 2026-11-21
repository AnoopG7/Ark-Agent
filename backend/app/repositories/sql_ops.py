"""PostgreSQL implementation of ``OpsRepository`` (SQLAlchemy 2.0, psycopg 3)."""

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload, sessionmaker

from app.db.models import (
    DepotRow,
    DispatchTaskRow,
    RouteRow,
    StockItemRow,
    StockReservationRow,
    TeamRow,
    TeamSkillRow,
    WardRow,
)
from app.db.seed.loader import SeedData, default_seed
from app.db.seeder import seed_database
from app.domain import (
    Depot,
    DispatchTask,
    ReliefPlan,
    ResourceType,
    Route,
    RouteStatus,
    StockItem,
    StockLevel,
    TaskStatus,
    Team,
    TeamSkill,
    TeamStatus,
    Ward,
)
from app.repositories.errors import NotFoundError
from app.repositories.rules import check_dispatch


# --- row → domain mapping ---------------------------------------------------------------
def _ward(row: WardRow) -> Ward:
    return Ward(id=row.id, name=row.name, population=row.population, zone=row.zone)


def _stock_item(row: StockItemRow) -> StockItem:
    return StockItem(
        resource=row.resource, unit=row.unit, quantity=row.quantity, reserved=row.reserved
    )


def _depot(row: DepotRow) -> Depot:
    return Depot(id=row.id, name=row.name, zone=row.zone, stock=[_stock_item(s) for s in row.stock])


def _route(row: RouteRow) -> Route:
    return Route(
        id=row.id,
        name=row.name,
        depot_id=row.depot_id,
        ward_id=row.ward_id,
        status=row.status,
        travel_minutes=row.travel_minutes,
        vehicle=row.vehicle,
        note=row.note,
    )


def _team(row: TeamRow) -> Team:
    return Team(
        id=row.id,
        name=row.name,
        skills=[s.skill for s in row.skills],
        size=row.size,
        status=row.status,
        base_depot=row.base_depot,
        vehicle=row.vehicle,
    )


def _task(row: DispatchTaskRow) -> DispatchTask:
    return DispatchTask(
        id=row.code,
        plan=ReliefPlan.model_validate(row.plan),
        status=row.status,
        created_at=row.created_at,
        decision_note=row.decision_note,
        thread_id=row.thread_id,
    )


class SqlOpsRepository:
    def __init__(self, session_factory: sessionmaker[Session], seed: SeedData | None = None):
        self._sf = session_factory
        self._seed = seed or default_seed()

    @contextmanager
    def _tx(self) -> Iterator[Session]:
        with self._sf.begin() as session:
            yield session

    # --- reads ---------------------------------------------------------------------------
    def list_wards(self) -> list[Ward]:
        with self._tx() as s:
            return [_ward(r) for r in s.scalars(select(WardRow).order_by(WardRow.id))]

    def get_ward(self, ward_id: str) -> Ward:
        with self._tx() as s:
            row = s.get(WardRow, ward_id)
            if row is None:
                raise NotFoundError(f"Unknown ward {ward_id}")
            return _ward(row)

    def list_depots(self) -> list[Depot]:
        with self._tx() as s:
            stmt = select(DepotRow).options(selectinload(DepotRow.stock)).order_by(DepotRow.id)
            return [_depot(r) for r in s.scalars(stmt)]

    def get_stock(self, resource: ResourceType, depot_id: str | None = None) -> list[StockLevel]:
        with self._tx() as s:
            if depot_id is not None and s.get(DepotRow, depot_id) is None:
                raise NotFoundError(f"Unknown depot {depot_id}")
            stmt = (
                select(StockItemRow, DepotRow.name)
                .join(DepotRow)
                .where(StockItemRow.resource == resource)
                .order_by(StockItemRow.depot_id)
            )
            if depot_id is not None:
                stmt = stmt.where(StockItemRow.depot_id == depot_id)
            return [
                StockLevel(
                    depot_id=item.depot_id,
                    depot_name=name,
                    resource=item.resource,
                    unit=item.unit,
                    quantity=item.quantity,
                    reserved=item.reserved,
                    available=item.quantity - item.reserved,
                )
                for item, name in s.execute(stmt)
            ]

    def list_routes(self, ward_id: str | None = None, route_id: str | None = None) -> list[Route]:
        with self._tx() as s:
            stmt = select(RouteRow).order_by(RouteRow.id)
            if ward_id is not None:
                stmt = stmt.where(RouteRow.ward_id == ward_id)
            if route_id is not None:
                stmt = stmt.where(RouteRow.id == route_id)
            return [_route(r) for r in s.scalars(stmt)]

    def update_route_status(
        self, route_id: str, status: RouteStatus, note: str | None = None
    ) -> Route:
        with self._tx() as s:
            row = s.get(RouteRow, route_id, with_for_update=True)
            if row is None:
                raise NotFoundError(f"Unknown route {route_id}")
            row.status = status
            if note is not None:
                row.note = note
            s.flush()
            return _route(row)

    def list_teams(
        self, skill: TeamSkill | None = None, status: TeamStatus | None = None
    ) -> list[Team]:
        with self._tx() as s:
            stmt = select(TeamRow).order_by(TeamRow.id)
            if skill is not None:
                stmt = stmt.where(TeamRow.skills.any(TeamSkillRow.skill == skill))
            if status is not None:
                stmt = stmt.where(TeamRow.status == status)
            return [_team(r) for r in s.scalars(stmt)]

    def list_tasks(self) -> list[DispatchTask]:
        with self._tx() as s:
            stmt = select(DispatchTaskRow).order_by(DispatchTaskRow.seq)
            return [_task(r) for r in s.scalars(stmt)]

    # --- writes --------------------------------------------------------------------------
    def dispatch(
        self, plan: ReliefPlan, note: str = "", thread_id: str | None = None
    ) -> DispatchTask:
        with self._tx() as s:
            # Lock the team and every stock row this plan touches, in a stable order, so
            # concurrent approvals serialise instead of over-drawing stock.
            team_row = s.get(TeamRow, plan.team_id, with_for_update=True)
            depot_ids = sorted(a.depot_id for a in plan.allocations)
            stock_rows = {
                r.depot_id: r
                for r in s.scalars(
                    select(StockItemRow)
                    .where(
                        StockItemRow.depot_id.in_(depot_ids),
                        StockItemRow.resource == plan.resource,
                    )
                    .order_by(StockItemRow.depot_id)
                    .with_for_update()
                )
            }
            existing_depots = set(s.scalars(select(DepotRow.id).where(DepotRow.id.in_(depot_ids))))
            route_ids = [a.route_id for a in plan.allocations]
            routes = {
                r.id: _route(r)
                for r in s.scalars(select(RouteRow).where(RouteRow.id.in_(route_ids)))
            }
            check_dispatch(
                plan,
                ward_exists=s.get(WardRow, plan.ward_id) is not None,
                team=_team(team_row) if team_row else None,
                routes=routes,
                stock={
                    d: (_stock_item(stock_rows[d]) if d in stock_rows else None)
                    for d in existing_depots
                },
            )
            for alloc in plan.allocations:
                stock_rows[alloc.depot_id].reserved += alloc.quantity
            team_row.status = TeamStatus.DEPLOYED
            row = self._insert_task(s, plan, TaskStatus.DISPATCHED, note, thread_id)
            row.reservations = [
                StockReservationRow(
                    depot_id=a.depot_id,
                    route_id=a.route_id,
                    resource=a.resource,
                    quantity=a.quantity,
                )
                for a in plan.allocations
            ]
            s.flush()
            return _task(row)

    def record_rejection(
        self, plan: ReliefPlan, note: str = "", thread_id: str | None = None
    ) -> DispatchTask:
        with self._tx() as s:
            if s.get(WardRow, plan.ward_id) is None:
                raise NotFoundError(f"Unknown ward {plan.ward_id}")
            if s.get(TeamRow, plan.team_id) is None:
                raise NotFoundError(f"Unknown team {plan.team_id}")
            return _task(self._insert_task(s, plan, TaskStatus.REJECTED, note, thread_id))

    def reset(self) -> None:
        with self._tx() as s:
            seed_database(s, self._seed, force=True)

    @staticmethod
    def _insert_task(
        s: Session, plan: ReliefPlan, status: TaskStatus, note: str, thread_id: str | None
    ) -> DispatchTaskRow:
        row = DispatchTaskRow(
            status=status,
            ward_id=plan.ward_id,
            team_id=plan.team_id,
            resource=plan.resource,
            plan=plan.model_dump(mode="json"),
            decision_note=note,
            thread_id=thread_id,
        )
        s.add(row)
        s.flush()
        row.code = f"TASK-{row.seq:04d}"
        s.flush()
        s.refresh(row)
        return row
