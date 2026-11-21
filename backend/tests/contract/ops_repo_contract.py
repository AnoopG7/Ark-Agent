"""Behavioural contract every ``OpsRepository`` implementation must satisfy.

Subclass ``OpsRepositoryContract`` and provide a ``repo`` fixture that yields a freshly seeded
repository.
"""

import pytest

from app.domain import ResourceType, RouteStatus, TaskStatus, TeamSkill, TeamStatus
from app.repositories.errors import ConflictError, InsufficientStockError, NotFoundError
from app.repositories.interfaces import OpsRepository
from tests.factories import make_plan


class OpsRepositoryContract:
    def test_satisfies_protocol(self, repo: OpsRepository) -> None:
        assert isinstance(repo, OpsRepository)

    # --- reads ---------------------------------------------------------------------------
    def test_lists_seeded_entities(self, repo: OpsRepository) -> None:
        assert len(repo.list_wards()) == 12
        assert [d.id for d in repo.list_depots()] == ["DEP-A", "DEP-B", "DEP-C"]
        assert len(repo.list_routes()) == 6
        assert repo.list_tasks() == []

    def test_get_ward_unknown_raises(self, repo: OpsRepository) -> None:
        assert repo.get_ward("W-07").name == "Ward 7"
        with pytest.raises(NotFoundError):
            repo.get_ward("W-99")

    def test_stock_all_depots_and_single_depot(self, repo: OpsRepository) -> None:
        levels = repo.get_stock(ResourceType.DRINKING_WATER)
        assert [(s.depot_id, s.available) for s in levels] == [
            ("DEP-A", 800),
            ("DEP-B", 1500),
            ("DEP-C", 600),
        ]
        only_b = repo.get_stock(ResourceType.DRINKING_WATER, depot_id="DEP-B")
        assert len(only_b) == 1 and only_b[0].depot_name == "Central Market Depot"

    def test_stock_unknown_depot_raises(self, repo: OpsRepository) -> None:
        with pytest.raises(NotFoundError):
            repo.get_stock(ResourceType.BOAT, depot_id="DEP-C2")

    def test_route_filters(self, repo: OpsRepository) -> None:
        assert {r.id for r in repo.list_routes(ward_id="W-07")} == {"RT-01", "RT-03", "RT-05"}
        assert repo.list_routes(route_id="RT-03")[0].status is RouteStatus.BLOCKED
        assert repo.list_routes(ward_id="W-02") == []

    def test_team_filters(self, repo: OpsRepository) -> None:
        medics = repo.list_teams(skill=TeamSkill.MEDICAL)
        assert {t.id for t in medics} == {"TM-04", "TM-05"}
        available_medics = repo.list_teams(skill=TeamSkill.MEDICAL, status=TeamStatus.AVAILABLE)
        assert [t.id for t in available_medics] == ["TM-04"]

    def test_update_route_status(self, repo: OpsRepository) -> None:
        route = repo.update_route_status("RT-03", RouteStatus.OPEN, note="Bridge reopened")
        assert route.status is RouteStatus.OPEN and route.note == "Bridge reopened"
        assert repo.list_routes(route_id="RT-03")[0].status is RouteStatus.OPEN
        with pytest.raises(NotFoundError):
            repo.update_route_status("RT-99", RouteStatus.OPEN)

    # --- dispatch ------------------------------------------------------------------------
    def test_dispatch_reserves_stock_and_deploys_team(self, repo: OpsRepository) -> None:
        task = repo.dispatch(make_plan(), note="approved by duty officer", thread_id="t1")
        assert task.status is TaskStatus.DISPATCHED
        assert task.id == "TASK-0001"
        assert task.thread_id == "t1"
        water = {s.depot_id: s for s in repo.get_stock(ResourceType.DRINKING_WATER)}
        assert water["DEP-A"].reserved == 800 and water["DEP-A"].available == 0
        assert water["DEP-C"].available == 500
        team = next(t for t in repo.list_teams() if t.id == "TM-01")
        assert team.status is TeamStatus.DEPLOYED
        assert repo.list_tasks() == [task]

    def test_reserve_insufficient_raises_and_leaves_stock(self, repo: OpsRepository) -> None:
        plan = make_plan(allocations=[("DEP-A", 801, "RT-01")], quantity_required=801)
        with pytest.raises(InsufficientStockError):
            repo.dispatch(plan)
        assert repo.get_stock(ResourceType.DRINKING_WATER, "DEP-A")[0].reserved == 0
        assert repo.list_tasks() == []

    def test_partial_failure_is_atomic(self, repo: OpsRepository) -> None:
        plan = make_plan(allocations=[("DEP-A", 100, "RT-01"), ("DEP-C", 999, "RT-05")])
        with pytest.raises(InsufficientStockError):
            repo.dispatch(plan)
        assert repo.get_stock(ResourceType.DRINKING_WATER, "DEP-A")[0].reserved == 0
        team = next(t for t in repo.list_teams() if t.id == "TM-01")
        assert team.status is TeamStatus.AVAILABLE

    def test_second_dispatch_cannot_overdraw(self, repo: OpsRepository) -> None:
        repo.dispatch(make_plan(allocations=[("DEP-A", 500, "RT-01")], team_id="TM-01"))
        with pytest.raises(InsufficientStockError):
            repo.dispatch(make_plan(allocations=[("DEP-A", 400, "RT-01")], team_id="TM-04"))
        assert repo.get_stock(ResourceType.DRINKING_WATER, "DEP-A")[0].available == 300

    def test_dispatch_over_blocked_route_conflicts(self, repo: OpsRepository) -> None:
        with pytest.raises(ConflictError, match="blocked"):
            repo.dispatch(make_plan(allocations=[("DEP-B", 900, "RT-03")]))

    def test_dispatch_route_must_link_depot_and_ward(self, repo: OpsRepository) -> None:
        with pytest.raises(ConflictError, match="does not connect"):
            repo.dispatch(make_plan(allocations=[("DEP-A", 100, "RT-02")]))

    def test_dispatching_a_deployed_team_conflicts(self, repo: OpsRepository) -> None:
        with pytest.raises(ConflictError, match="not available"):
            repo.dispatch(make_plan(team_id="TM-05"))

    def test_dispatch_unknown_team_or_ward(self, repo: OpsRepository) -> None:
        with pytest.raises(NotFoundError):
            repo.dispatch(make_plan(team_id="TM-99"))
        with pytest.raises(NotFoundError):
            repo.dispatch(make_plan(ward_id="W-99"))

    def test_record_rejection_reserves_nothing(self, repo: OpsRepository) -> None:
        task = repo.record_rejection(make_plan(), note="use boats instead")
        assert task.status is TaskStatus.REJECTED and task.decision_note == "use boats instead"
        assert repo.get_stock(ResourceType.DRINKING_WATER, "DEP-A")[0].reserved == 0

    def test_record_rejection_unknown_team_raises(self, repo: OpsRepository) -> None:
        with pytest.raises(NotFoundError):
            repo.record_rejection(make_plan(team_id="TM-99"))

    def test_task_ids_increment(self, repo: OpsRepository) -> None:
        a = repo.record_rejection(make_plan())
        b = repo.record_rejection(make_plan())
        assert (a.id, b.id) == ("TASK-0001", "TASK-0002")

    def test_reset_restores_seed(self, repo: OpsRepository) -> None:
        repo.dispatch(make_plan())
        repo.update_route_status("RT-03", RouteStatus.OPEN)
        repo.reset()
        assert repo.get_stock(ResourceType.DRINKING_WATER, "DEP-A")[0].reserved == 0
        assert repo.list_routes(route_id="RT-03")[0].status is RouteStatus.BLOCKED
        assert repo.list_tasks() == []
