import pytest
from langchain_core.tools import BaseTool

from app.domain import ToolResult
from app.repositories.memory_ops import InMemoryOpsRepository
from app.tools.context import ToolContext
from app.tools.executor import run_tool
from app.tools.registry import APPROVAL_REQUIRED, build_tools


@pytest.fixture
def tools() -> dict[str, BaseTool]:
    return {t.name: t for t in build_tools(ToolContext(repo=InMemoryOpsRepository()))}


def test_registry_contents(tools: dict[str, BaseTool]) -> None:
    assert set(tools) == {
        "situation_report",
        "stock_lookup",
        "road_status",
        "list_teams",
        "create_dispatch_task",
    }
    assert set(APPROVAL_REQUIRED) == {"create_dispatch_task"}


def test_stock_lookup_totals(tools: dict[str, BaseTool]) -> None:
    res = run_tool(tools["stock_lookup"], {"resource": "drinking_water"})
    assert res.ok
    assert res.data["total_available"] == 2900
    assert res.data["unit"] == "litre"
    assert len(res.data["depots"]) == 3


def test_stock_lookup_single_depot(tools: dict[str, BaseTool]) -> None:
    res = run_tool(tools["stock_lookup"], {"resource": "boat", "depot_id": "DEP-C"})
    assert res.ok and res.data["total_available"] == 6


def test_road_status_ward7_shows_blocked_route_sorted(tools: dict[str, BaseTool]) -> None:
    res = run_tool(tools["road_status"], {"ward_id": "W-07"})
    routes = res.data["routes"]
    assert [r["id"] for r in routes] == ["RT-03", "RT-01", "RT-05"]
    assert routes[0]["usable"] is False


def test_road_status_ward_without_routes(tools: dict[str, BaseTool]) -> None:
    res = run_tool(tools["road_status"], {"ward_id": "W-02"})
    assert res.ok and res.data["routes"] == [] and "No route" in res.data["message"]


def test_list_teams_defaults_to_available(tools: dict[str, BaseTool]) -> None:
    res = run_tool(tools["list_teams"], {"skill": "medical"})
    assert [t["id"] for t in res.data["teams"]] == ["TM-04"]


@pytest.mark.parametrize(
    ("tool", "args", "fragment"),
    [
        ("stock_lookup", {"resource": "gold"}, "resource"),
        ("stock_lookup", {"resource": "boat", "depot_id": "DEP-Z"}, "depot_id"),
        ("road_status", {"ward_id": "Ward 7"}, "ward_id"),
        ("road_status", {"ward_id": "W-99"}, "Unknown ward"),
        ("list_teams", {"skill": "cooking"}, "skill"),
        ("create_dispatch_task", {"ward_id": "W-07", "people": -5}, "Invalid arguments"),
    ],
)
def test_tools_return_error_on_invalid_args(
    tools: dict[str, BaseTool], tool: str, args: dict, fragment: str
) -> None:
    res = run_tool(tools[tool], args)
    assert isinstance(res, ToolResult)
    assert not res.ok
    assert fragment in res.error


def test_dispatch_tool_never_executes_directly(tools: dict[str, BaseTool]) -> None:
    plan = {
        "ward_id": "W-07",
        "resource": "drinking_water",
        "people": 300,
        "quantity_required": 900,
        "allocations": [
            {
                "depot_id": "DEP-A",
                "resource": "drinking_water",
                "quantity": 800,
                "route_id": "RT-01",
            }
        ],
        "team_id": "TM-01",
        "eta_minutes": 75,
        "rationale": "x",
    }
    res = run_tool(tools["create_dispatch_task"], plan)
    assert not res.ok and "approval" in res.error


def test_situation_report_combines_stock_routes_and_teams(tools: dict[str, BaseTool]) -> None:
    res = run_tool(tools["situation_report"], {"ward_id": "W-07", "resource": "drinking_water"})
    assert res.ok
    d = res.data
    assert d["total_available"] == 2900
    assert [r["id"] for r in d["routes"]] == ["RT-03", "RT-01", "RT-05"]
    assert d["routes"][0]["usable"] is False
    assert "TM-01" in {t["id"] for t in d["available_teams"]}
    assert "TM-05" not in {t["id"] for t in d["available_teams"]}  # deployed


def test_situation_report_filters_teams_by_required_skill(tools: dict[str, BaseTool]) -> None:
    res = run_tool(tools["situation_report"], {"ward_id": "W-12", "resource": "medicine_kit"})
    assert res.data["required_skill"] == "medical"
    assert {t["id"] for t in res.data["available_teams"]} == {"TM-04"}


def test_situation_report_unknown_ward_is_an_observation(tools: dict[str, BaseTool]) -> None:
    res = run_tool(tools["situation_report"], {"ward_id": "W-99", "resource": "blanket"})
    assert not res.ok
