from langchain_core.messages import AIMessage

from app.domain import ResourceType
from app.evaluation.metrics import ToolCallRecord, duplicate_calls, unnecessary_calls
from app.evaluation.report import summary_markdown, trace_markdown
from app.evaluation.runner import ScenarioRunner, to_json
from app.evaluation.scenarios import SCENARIOS
from tests.fakes import FakeToolCallingModel, ai, call
from tests.unit.test_graph import WATER_PLAN


def rec(turn: int, name: str, **args) -> ToolCallRecord:
    return ToolCallRecord(request=turn, step=1, name=name, args=args)


def test_duplicates_within_a_turn_only() -> None:
    calls = [
        rec(0, "stock_lookup", resource="drinking_water"),
        rec(0, "stock_lookup", resource="drinking_water"),
        rec(0, "road_status", ward_id="W-07"),
        rec(1, "stock_lookup", resource="drinking_water"),  # new turn: legitimate re-check
    ]
    assert duplicate_calls(calls) == [calls[1]]


def test_irrelevant_resource_lookups_are_unnecessary() -> None:
    calls = [rec(0, "stock_lookup", resource="blanket"), rec(0, "list_teams")]
    found = unnecessary_calls(calls, {ResourceType.DRINKING_WATER})
    assert [c.args for c in found] == [{"resource": "blanket"}]


def test_scenarios_cover_case_study_requirements() -> None:
    ids = {s.id for s in SCENARIOS}
    assert len(SCENARIOS) >= 6
    assert {"S2", "S3", "S4"} <= ids  # blocked road, insufficient stock, step limit


def test_runner_and_report_with_fake_llm(retriever_for_eval) -> None:
    scenario = next(s for s in SCENARIOS if s.id == "S2")
    llm = FakeToolCallingModel(
        responses=[
            ai(call("search_guidelines", query="drinking water litres per person per day")),
            ai(
                call("stock_lookup", resource="drinking_water"), call("road_status", ward_id="W-07")
            ),
            ai(call("stock_lookup", resource="drinking_water")),  # duplicate in same turn
            ai(call("create_dispatch_task", **WATER_PLAN)),
        ]
    )
    record = ScenarioRunner(llm, retriever_for_eval).run(scenario)
    assert record.error is None
    assert record.final_status == "dispatched"
    assert record.passed, record.check_results
    assert len(record.unnecessary) == 1
    assert record.approval_respected
    data = to_json(record)
    assert data["metrics"]["dispatched_plans_valid_against_seed"] == [True]
    assert "Approval requested" in trace_markdown(data)
    assert "| [S2](traces/S2.md)" in summary_markdown([data], "fake")


def test_runner_records_deviation_when_no_proposal(retriever_for_eval) -> None:
    scenario = next(s for s in SCENARIOS if s.id == "S1")
    llm = FakeToolCallingModel(responses=[AIMessage(content="Which ward?")])
    record = ScenarioRunner(llm, retriever_for_eval).run(scenario)
    assert record.deviations and not record.passed
