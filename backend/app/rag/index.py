"""Vector index interface."""

from typing import Protocol

from app.rag.types import Chunk, ScoredChunk


class VectorIndex(Protocol):
    def ids(self) -> set[str]: ...

    def upsert(self, chunks: list[Chunk], vectors: list[list[float]]) -> None: ...

    def delete(self, ids: set[str]) -> None: ...

    def search(self, vector: list[float], k: int) -> list[ScoredChunk]:
        """Top-``k`` chunks by cosine similarity, best first."""
        ...
