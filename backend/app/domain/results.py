from typing import Any, Self

from pydantic import model_validator

from app.domain.base import DomainModel


class ToolResult(DomainModel):
    """Uniform envelope returned by every agent tool."""

    ok: bool
    data: Any = None
    error: str | None = None

    @model_validator(mode="after")
    def _ok_xor_error(self) -> Self:
        if self.ok and self.error is not None:
            raise ValueError("a successful result cannot carry an error")
        if not self.ok and not self.error:
            raise ValueError("a failed result must carry an error message")
        return self

    @classmethod
    def success(cls, data: Any = None) -> "ToolResult":
        return cls(ok=True, data=data)

    @classmethod
    def failure(cls, error: str) -> "ToolResult":
        return cls(ok=False, error=error)
