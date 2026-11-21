"""The side-effecting dispatch tool. It is declared to the LLM but never executed directly:
the agent graph routes every call to it through the coordinator approval checkpoint."""

from langchain_core.tools import BaseTool, StructuredTool

from app.domain import ReliefPlan, ToolResult

DISPATCH_TOOL_NAME = "create_dispatch_task"


def _blocked(**_: object) -> ToolResult:
    return ToolResult.failure(
        "create_dispatch_task requires coordinator approval and cannot be executed directly."
    )


def build_dispatch_tool() -> BaseTool:
    return StructuredTool.from_function(
        _blocked,
        name=DISPATCH_TOOL_NAME,
        description=(
            "Propose dispatching a team with supplies. Pauses for coordinator approval; on "
            "approval stock is reserved and the team deployed. Only call once stock, routes and "
            "team availability have been checked. Use only usable (not blocked) routes that "
            "connect each depot to the ward."
        ),
        args_schema=ReliefPlan,
    )
