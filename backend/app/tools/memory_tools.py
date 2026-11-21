"""Tools that let the agent read and write long-term operational memory."""

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool, StructuredTool
from pydantic import Field

from app.domain import FactKind, MemoryFact, ToolResult
from app.domain.base import DomainModel, WardId
from app.memory.facts import FactsService


class RememberFactArgs(DomainModel):
    kind: FactKind = Field(description="decision, reservation, road_report, rejection or note")
    content: str = Field(
        min_length=5, max_length=500, description="One sentence with ward, quantity and depot"
    )
    ward_id: WardId | None = Field(default=None, description="Ward the fact is about, e.g. W-07")


class RecallFactsArgs(DomainModel):
    ward_id: WardId | None = Field(default=None, description="Only facts about this ward")
    kind: FactKind | None = Field(default=None, description="Only facts of this kind")


def _thread_id(config: RunnableConfig | None) -> str | None:
    return ((config or {}).get("configurable") or {}).get("thread_id")


def build_memory_tools(facts: FactsService) -> list[BaseTool]:
    def remember_fact(
        kind: FactKind, content: str, ward_id: str | None = None, config: RunnableConfig = None
    ) -> ToolResult:
        fact = facts.save(
            MemoryFact(
                kind=kind, content=content, ward_id=ward_id, source_thread=_thread_id(config)
            )
        )
        return ToolResult.success({"saved": fact.model_dump(mode="json")})

    def recall_facts(ward_id: str | None = None, kind: FactKind | None = None) -> ToolResult:
        found = facts.list(ward_id=ward_id, kind=kind, limit=10)
        return ToolResult.success(
            {
                "facts": [f.model_dump(mode="json", exclude={"id"}) for f in found],
                "message": None if found else "Nothing remembered for this filter.",
            }
        )

    return [
        StructuredTool.from_function(
            remember_fact,
            name="remember_fact",
            description=(
                "Save an operational fact to long-term memory so later conversations and shifts "
                "can see it (e.g. a road report from a coordinator)."
            ),
            args_schema=RememberFactArgs,
        ),
        StructuredTool.from_function(
            recall_facts,
            name="recall_facts",
            description=(
                "Read remembered operational facts (earlier dispatches, reservations, rejections, "
                "road reports), newest first."
            ),
            args_schema=RecallFactsArgs,
        ),
    ]
