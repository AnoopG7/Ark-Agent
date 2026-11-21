from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.domain import (
    Allocation,
    Depot,
    DispatchTask,
    MemoryFact,
    ReliefPlan,
    ReliefRequest,
    ResourceType,
    Route,
    StockItem,
    TaskStatus,
    Team,
    ToolResult,
    Unit,
)


def _alloc(depot: str, qty: int, route: str, resource: str = "drinking_water") -> dict:
    return {"depot_id": depot, "resource": resource, "quantity": qty, "route_id": route}


def _plan(**overrides) -> ReliefPlan:
    data = {
        "ward_id": "W-07",
        "resource": "drinking_water",
        "people": 300,
        "quantity_required": 1200,
        "allocations": [
            _alloc("DEP-A", 800, "RT-01"),
            _alloc("DEP-C", 400, "RT-05"),
        ],
        "team_id": "TM-01",
        "eta_minutes": 90,
        "rationale": "Split across two depots because RT-03 is blocked.",
        "citations": ["sop-water-supply.md#daily-allowance"],
    }
    data.update(overrides)
    return ReliefPlan.model_validate(data)


class TestStockItem:
    def test_available_is_quantity_minus_reserved(self) -> None:
        item = StockItem(resource=ResourceType.DRINKING_WATER, quantity=1000, reserved=200)
        assert item.available == 800
        assert item.unit is Unit.LITRE

    def test_reserved_cannot_exceed_quantity(self) -> None:
        with pytest.raises(ValidationError, match="reserved"):
            StockItem(resource="food_ration", quantity=10, reserved=11)

    def test_negative_quantity_rejected(self) -> None:
        with pytest.raises(ValidationError):
            StockItem(resource="food_ration", quantity=-1)

    def test_wrong_unit_for_resource_rejected(self) -> None:
        with pytest.raises(ValidationError, match="unit"):
            StockItem(resource="drinking_water", quantity=5, unit="kit")


class TestDepotAndRoute:
    def test_bad_depot_id_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Depot(id="DEP-Z", name="Nowhere", zone="x", stock=[])

    def test_duplicate_stock_resource_rejected(self) -> None:
        with pytest.raises(ValidationError, match="duplicate"):
            Depot(
                id="DEP-A",
                name="A",
                zone="north",
                stock=[
                    StockItem(resource="blanket", quantity=1),
                    StockItem(resource="blanket", quantity=2),
                ],
            )

    def test_depot_item_lookup(self) -> None:
        depot = Depot(
            id="DEP-A", name="A", zone="north", stock=[StockItem(resource="blanket", quantity=4)]
        )
        assert depot.item(ResourceType.BLANKET).quantity == 4
        assert depot.item(ResourceType.BOAT) is None

    def test_route_id_pattern(self) -> None:
        with pytest.raises(ValidationError):
            Route(
                id="R1",
                name="x",
                depot_id="DEP-A",
                ward_id="W-01",
                status="open",
                travel_minutes=10,
                vehicle="truck",
            )

    def test_extra_fields_forbidden(self) -> None:
        with pytest.raises(ValidationError, match="extra"):
            Team(
                id="TM-01",
                name="Alpha",
                skills=["logistics"],
                size=6,
                status="available",
                base_depot="DEP-A",
                vehicle="truck",
                rank="captain",
            )


class TestRequestAndPlan:
    def test_request_requires_positive_people(self) -> None:
        with pytest.raises(ValidationError):
            ReliefRequest(ward_id="W-07", resource="drinking_water", people=0)

    def test_plan_totals_and_shortfall(self) -> None:
        plan = _plan()
        assert plan.total_allocated == 1200
        assert plan.shortfall == 0

    def test_plan_reports_shortfall(self) -> None:
        plan = _plan(
            quantity_required=1500,
        )
        assert plan.shortfall == 300

    def test_plan_requires_allocations(self) -> None:
        with pytest.raises(ValidationError):
            _plan(allocations=[])

    def test_allocation_resource_must_match_plan(self) -> None:
        with pytest.raises(ValidationError, match="resource"):
            _plan(allocations=[_alloc("DEP-A", 10, "RT-01", resource="food_ration")])

    def test_one_allocation_per_depot(self) -> None:
        alloc = _alloc("DEP-A", 10, "RT-01")
        with pytest.raises(ValidationError, match="depot"):
            _plan(allocations=[alloc, alloc])

    def test_citation_format(self) -> None:
        with pytest.raises(ValidationError):
            _plan(citations=["just some text"])

    def test_allocation_quantity_positive(self) -> None:
        with pytest.raises(ValidationError):
            Allocation(depot_id="DEP-A", resource="boat", quantity=0, route_id="RT-01")


class TestTaskFactAndToolResult:
    def test_dispatch_task_roundtrip(self) -> None:
        task = DispatchTask(
            id="TASK-0001",
            plan=_plan(),
            status=TaskStatus.DISPATCHED,
            created_at=datetime.now(UTC),
        )
        again = DispatchTask.model_validate_json(task.model_dump_json())
        assert again == task

    def test_memory_fact_content_bounds(self) -> None:
        with pytest.raises(ValidationError):
            MemoryFact(kind="note", content="")

    def test_memory_fact_defaults(self) -> None:
        fact = MemoryFact(
            kind="reservation", content="Depot B reserved 200 L for Ward 7", ward_id="W-07"
        )
        assert fact.id
        assert fact.created_at.tzinfo is not None

    def test_tool_result_ok_xor_error(self) -> None:
        assert ToolResult.success({"x": 1}).ok
        assert ToolResult.failure("boom").error == "boom"
        with pytest.raises(ValidationError):
            ToolResult(ok=True, error="contradiction")
        with pytest.raises(ValidationError):
            ToolResult(ok=False)
