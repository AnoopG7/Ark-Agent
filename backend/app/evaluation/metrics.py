"""Agent behaviour metrics computed from a recorded run (PDF task 6)."""

import json
from collections import Counter
from dataclasses import dataclass

from app.domain import ResourceType


@dataclass
class ToolCallRecord:
    request: int
    """Index of the coordinator turn (message or approval decision) this call served."""
    step: int
    name: str
    args: dict
    ok: bool | None = None
    error: str | None = None

    @property
    def key(self) -> tuple[int, str, str]:
        return (self.request, self.name, json.dumps(self.args, sort_keys=True))


def duplicate_calls(calls: list[ToolCallRecord]) -> list[ToolCallRecord]:
    """Calls repeating an earlier identical call (same tool, same args) within the same turn.

    Re-checking stock or roads after a coordinator decision is legitimate (state may have
    changed), so calls are only compared within one coordinator turn.
    """
    seen: set[tuple[int, str, str]] = set()
    dupes = []
    for c in calls:
        if c.name == "create_dispatch_task":
            continue
        if c.key in seen:
            dupes.append(c)
        seen.add(c.key)
    return dupes


def irrelevant_calls(
    calls: list[ToolCallRecord], resources: set[ResourceType]
) -> list[ToolCallRecord]:
    """Stock lookups for resources the scenario never needed."""
    wanted = {r.value for r in resources}
    return [c for c in calls if c.name == "stock_lookup" and c.args.get("resource") not in wanted]


def unnecessary_calls(
    calls: list[ToolCallRecord], resources: set[ResourceType]
) -> list[ToolCallRecord]:
    dupes = duplicate_calls(calls)
    irrelevant = [c for c in irrelevant_calls(calls, resources) if c not in dupes]
    return dupes + irrelevant


def tool_histogram(calls: list[ToolCallRecord]) -> dict[str, int]:
    return dict(Counter(c.name for c in calls))
