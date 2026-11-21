"""Assembles the tool set the agent can use for a given context."""

from langchain_core.tools import BaseTool

from app.tools.context import ToolContext
from app.tools.dispatch import DISPATCH_TOOL_NAME, build_dispatch_tool
from app.tools.ops_tools import build_ops_tools

APPROVAL_REQUIRED: frozenset[str] = frozenset({DISPATCH_TOOL_NAME})
"""Tools with side effects that must pause for coordinator approval."""


def build_tools(ctx: ToolContext) -> list[BaseTool]:
    tools = [*build_ops_tools(ctx)]
    if ctx.retriever is not None:
        from app.tools.guidelines import build_guideline_tool

        tools.append(build_guideline_tool(ctx.retriever))
    if ctx.facts is not None:
        from app.tools.memory_tools import build_memory_tools

        tools.extend(build_memory_tools(ctx.facts))
    tools.append(build_dispatch_tool())
    return tools
