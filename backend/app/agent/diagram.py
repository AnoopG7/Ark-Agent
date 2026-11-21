"""Render the planning graph structure without an LLM or database."""

from typing import Any

from langchain_core.language_models import BaseChatModel

from app.agent.graph import build_graph
from app.repositories.memory_ops import InMemoryOpsRepository


class _StructureOnlyModel(BaseChatModel):
    """Placeholder model: lets the graph be compiled for drawing; never invoked."""

    @property
    def _llm_type(self) -> str:
        return "structure-only"

    def bind_tools(self, tools: Any, **kwargs: Any) -> "_StructureOnlyModel":
        return self

    def _generate(self, *args: Any, **kwargs: Any):
        raise RuntimeError("The diagram model cannot generate text.")


def graph_mermaid() -> str:
    graph = build_graph(llm=_StructureOnlyModel(), repo=InMemoryOpsRepository())
    return graph.get_graph().draw_mermaid()
