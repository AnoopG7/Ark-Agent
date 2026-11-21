import pytest

from app.agent.validator import validate_plan
from app.repositories.memory_ops import InMemoryOpsRepository
from tests.factories import make_plan

CITE = "sop-water-supply.md#daily-allowance"


@pytest.fixture
def repo() -> InMemoryOpsRepository:
    return InMemoryOpsRepository()


def test_valid_plan_has_no_violations(repo) -> None:
    plan = make_plan(eta_minutes=135, citations=[CITE])
    assert validate_plan(plan, repo, {CITE}) == []


@pytest.mark.parametrize(
    ("overrides", "fragment"),
    [
        ({"allocations": [("DEP-B", 900, "RT-03")]}, "blocked"),
        ({"allocations": [("DEP-A", 900, "RT-01")]}, "only 800"),
        ({"allocations": [("DEP-A", 100, "RT-02")]}, "not DEP-A->W-07"),
        ({"quantity_required": 500}, "below the SOP minimum of 900"),
        ({"team_id": "TM-05"}, "deployed"),
        ({"team_id": "TM-08"}, "travels by boat"),
        ({"eta_minutes": 30}, "slowest route"),
        ({"citations": ["sop-made-up.md#x"]}, "not retrieved"),
        ({"ward_id": "W-99"}, "does not exist"),
    ],
)
def test_violations(repo, overrides, fragment) -> None:
    plan = make_plan(**{"eta_minutes": 135, **overrides})
    violations = validate_plan(plan, repo, {CITE})
    assert any(fragment in v for v in violations), violations


def test_boat_route_needs_boat_crew(repo) -> None:
    plan = make_plan(
        ward_id="W-09", allocations=[("DEP-B", 900, "RT-04")], team_id="TM-01", eta_minutes=65
    )
    assert any("boat-only" in v for v in validate_plan(plan, repo))
    ok = make_plan(
        ward_id="W-09", allocations=[("DEP-B", 900, "RT-04")], team_id="TM-03", eta_minutes=65
    )
    assert validate_plan(ok, repo) == []


def test_medicine_requires_medical_team(repo) -> None:
    plan = make_plan(
        resource="medicine_kit",
        people=100,
        quantity_required=2,
        allocations=[("DEP-A", 2, "RT-01")],
        team_id="TM-01",
    )
    assert any("medical" in v for v in validate_plan(plan, repo))
