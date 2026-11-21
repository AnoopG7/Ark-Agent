"""RAG tool: search the relief SOP knowledge base."""

from langchain_core.tools import BaseTool, StructuredTool
from pydantic import Field

from app.domain import ToolResult
from app.domain.base import DomainModel
from app.rag.retriever import Retriever

GUIDELINE_TOOL_NAME = "search_guidelines"


class SearchGuidelinesArgs(DomainModel):
    query: str = Field(min_length=3, max_length=300, description="What you need to know")
    k: int = Field(default=3, ge=1, le=5, description="Number of passages")


def build_guideline_tool(retriever: Retriever) -> BaseTool:
    def search_guidelines(query: str, k: int = 3) -> ToolResult:
        hits = retriever.search(query, k)
        return ToolResult.success(
            {
                "results": [h.model_dump() for h in hits],
                "message": None if hits else "No relevant guideline found.",
            }
        )

    return StructuredTool.from_function(
        search_guidelines,
        name=GUIDELINE_TOOL_NAME,
        description=(
            "Search the centre's relief SOPs (water allowance per person, ration sizes, medicine "
            "kit ratios, boat capacity, route rules, dispatch protocol). Cite results in the plan "
            "using their 'citation' value exactly."
        ),
        args_schema=SearchGuidelinesArgs,
    )
