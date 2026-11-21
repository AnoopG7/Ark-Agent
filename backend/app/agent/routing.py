"""Conditional edges of the planning graph."""

from typing import Literal

from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig

from app.agent.state import AgentState
from app.tools.registry import APPROVAL_REQUIRED

Route = Literal["tools", "approval", "finalize_plan"]


def make_route_after_reason(default_max_steps: int):
    def route_after_reason(state: AgentState, config: RunnableConfig) -> Route:
        """Decide what follows a reasoning step.

        * no tool calls                      -> finalize_plan (the agent answered or asked)
        * step budget exhausted              -> finalize_plan (stop condition)
        * any call needs approval (dispatch) -> approval (human checkpoint)
        * otherwise                          -> tools (observe and loop back)
        """
        last = state["messages"][-1]
        if not isinstance(last, AIMessage) or not last.tool_calls:
            return "finalize_plan"
        max_steps = int((config.get("configurable") or {}).get("max_steps", default_max_steps))
        if state.get("step_count", 0) >= max_steps:
            return "finalize_plan"
        if any(c["name"] in APPROVAL_REQUIRED for c in last.tool_calls):
            return "approval"
        return "tools"

    return route_after_reason
