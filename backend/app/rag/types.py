"""Value types shared by the RAG pipeline."""

from pydantic import Field

from app.domain.base import DomainModel


class Chunk(DomainModel):
    """A retrievable piece of a knowledge document. ``id`` is a hash of its content."""

    id: str
    source: str = Field(description="File name, e.g. sop-water-supply.md")
    section: str = Field(description="Slug of the section heading, e.g. daily-allowance")
    title: str = Field(description="Document title and section heading for display")
    text: str

    @property
    def citation(self) -> str:
        return f"{self.source}#{self.section}"


class ScoredChunk(DomainModel):
    chunk: Chunk
    score: float = Field(description="Cosine similarity in [-1, 1]; higher is closer")


class SyncStats(DomainModel):
    """Outcome of synchronising the index with the knowledge directory."""

    added: int
    removed: int
    unchanged: int
