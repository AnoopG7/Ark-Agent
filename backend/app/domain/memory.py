from datetime import UTC, datetime
from uuid import uuid4

from pydantic import AwareDatetime, Field

from app.domain.base import DomainModel, WardId
from app.domain.enums import FactKind


class MemoryFact(DomainModel):
    """A durable operational fact remembered across conversations and shifts."""

    id: str = Field(default_factory=lambda: uuid4().hex)
    kind: FactKind
    content: str = Field(min_length=1, max_length=500)
    ward_id: WardId | None = None
    created_at: AwareDatetime = Field(default_factory=lambda: datetime.now(UTC))
    source_thread: str | None = None
