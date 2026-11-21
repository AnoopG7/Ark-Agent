"""In-memory vector index (brute-force cosine) used by unit tests."""

import math

from app.rag.types import Chunk, ScoredChunk


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return dot / (na * nb)


class InMemoryVectorIndex:
    def __init__(self) -> None:
        self._items: dict[str, tuple[Chunk, list[float]]] = {}

    def ids(self) -> set[str]:
        return set(self._items)

    def upsert(self, chunks: list[Chunk], vectors: list[list[float]]) -> None:
        for chunk, vec in zip(chunks, vectors, strict=True):
            self._items[chunk.id] = (chunk, vec)

    def delete(self, ids: set[str]) -> None:
        for i in ids:
            self._items.pop(i, None)

    def search(self, vector: list[float], k: int) -> list[ScoredChunk]:
        scored = [ScoredChunk(chunk=c, score=_cosine(vector, v)) for c, v in self._items.values()]
        return sorted(scored, key=lambda s: s.score, reverse=True)[:k]
