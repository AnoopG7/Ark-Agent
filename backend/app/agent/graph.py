"""Assembly of the ReAct planning graph.

START -> load_memory -> reason --(tool calls)--> tools -> reason
                          |  \\--(dispatch)--> approval --(approve/reject)--> finalize_plan
                          |                      \\--(revise / invalid plan)--> reason
                          \\--(answer / step limit)--> finalize_plan -> END
"""

from langchain_core.language_models import BaseChatModel
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.store.base import BaseStore

from app.agent.nodes import AgentNodes
from app.agent.routing import make_route_after_reason
from app.agent.state import AgentState
from app.memory.facts import FactsService
from app.repositories.interfaces import OpsRepository
from app.tools.context import ToolContext
from app.tools.registry import build_tools


def build_graph(
    *,
    llm: BaseChatModel,
    repo: OpsRepository,
    checkpointer: BaseCheckpointSaver | None = None,
    store: BaseStore | None = None,
    retriever=None,
    max_steps: int = 8,
) -> CompiledStateGraph:
    facts = FactsService(store) if store is not None else None
    tools = build_tools(ToolContext(repo=repo, retriever=retriever, facts=facts))
    nodes = AgentNodes(llm=llm, tools=tools, repo=repo, facts=facts, max_steps=max_steps)

    builder = StateGraph(AgentState)
    builder.add_node("load_memory", nodes.load_memory)
    builder.add_node("reason", nodes.reason)
    builder.add_node("tools", nodes.run_tools)
    builder.add_node("approval", nodes.approval, destinations=("reason", "finalize_plan"))
    builder.add_node("finalize_plan", nodes.finalize_plan)

    builder.add_edge(START, "load_memory")
    builder.add_edge("load_memory", "reason")
    builder.add_conditional_edges(
        "reason",
        make_route_after_reason(max_steps),
        {"tools": "tools", "approval": "approval", "finalize_plan": "finalize_plan"},
    )
    builder.add_edge("tools", "reason")
    builder.add_edge("finalize_plan", END)
    return builder.compile(checkpointer=checkpointer, store=store, name="ark-relief-planner")
