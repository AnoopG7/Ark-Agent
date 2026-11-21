"""Safe tool execution: every outcome becomes a ``ToolResult``, never an exception."""

from typing import Any

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool
from pydantic import ValidationError

from app.domain import ToolResult
from app.repositories.errors import RepositoryError


def _format_validation(exc: ValidationError) -> str:
    parts = []
    for err in exc.errors()[:5]:
        loc = ".".join(str(p) for p in err["loc"]) or "arguments"
        parts.append(f"{loc}: {err['msg']}")
    return "Invalid arguments - " + "; ".join(parts)


def run_tool(
    tool: BaseTool, args: dict[str, Any], config: RunnableConfig | None = None
) -> ToolResult:
    """Validate ``args`` against the tool schema, run it and normalise the outcome."""
    try:
        result = tool.invoke(args, config=config)
    except ValidationError as exc:
        return ToolResult.failure(_format_validation(exc))
    except RepositoryError as exc:
        return ToolResult.failure(str(exc))
    except Exception as exc:  # noqa: BLE001 - surfaced to the agent rather than crashing the run
        return ToolResult.failure(f"{type(exc).__name__}: {exc}")
    if isinstance(result, ToolResult):
        return result
    return ToolResult.success(result)
