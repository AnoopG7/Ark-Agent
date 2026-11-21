"""Base model and constrained identifier types used by every domain schema."""

from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, StringConstraints, model_validator


class DomainModel(BaseModel):
    """Strict base model: unknown fields are rejected and strings are trimmed.

    Computed fields (e.g. ``StockItem.available``) appear in serialised output; they are dropped
    on input so a dumped model always validates back into an equal model.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, validate_assignment=True)

    @model_validator(mode="before")
    @classmethod
    def _drop_computed_fields(cls, data: Any) -> Any:
        if isinstance(data, dict) and cls.model_computed_fields:
            return {k: v for k, v in data.items() if k not in cls.model_computed_fields}
        return data


DepotId = Annotated[str, StringConstraints(pattern=r"^DEP-[A-C]$")]
RouteId = Annotated[str, StringConstraints(pattern=r"^RT-\d{2}$")]
TeamId = Annotated[str, StringConstraints(pattern=r"^TM-\d{2}$")]
WardId = Annotated[str, StringConstraints(pattern=r"^W-\d{2}$")]
TaskId = Annotated[str, StringConstraints(pattern=r"^TASK-\d{4,}$")]
Citation = Annotated[str, StringConstraints(pattern=r"^[\w.-]+\.md#[\w-]+$")]
"""A guideline citation in the form ``<source file>#<section slug>``."""
NonEmptyStr = Annotated[str, StringConstraints(min_length=1, max_length=200)]
