"""Dependencies the agent tools operate on."""

from dataclasses import dataclass, field
from typing import Any

from app.repositories.interfaces import OpsRepository


@dataclass(frozen=True)
class ToolContext:
    """Everything a tool needs. Optional services are wired in when available."""

    repo: OpsRepository
    retriever: Any | None = None  # app.rag.retriever.Retriever
    facts: Any | None = None  # app.memory.facts.FactsService
    extras: dict[str, Any] = field(default_factory=dict)
