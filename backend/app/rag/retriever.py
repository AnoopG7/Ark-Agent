"""Query-side retrieval with a similarity threshold."""

from pydantic import Field

from app.domain.base import DomainModel
from app.rag.embeddings import Embedder
from app.rag.index import VectorIndex


class RetrievedGuideline(DomainModel):
    citation: str = Field(description="Cite as <source>#<section>")
    title: str
    text: str
    score: float


class Retriever:
    def __init__(
        self, embedder: Embedder, index: VectorIndex, top_k: int = 3, min_score: float = 0.35
    ) -> None:
        self._embedder = embedder
        self._index = index
        self.top_k = top_k
        self.min_score = min_score

    def search(self, query: str, k: int | None = None) -> list[RetrievedGuideline]:
        hits = self._index.search(self._embedder.embed_query(query), k or self.top_k)
        return [
            RetrievedGuideline(
                citation=h.chunk.citation,
                title=h.chunk.title,
                text=h.chunk.text,
                score=round(h.score, 4),
            )
            for h in hits
            if h.score >= self.min_score
        ]
