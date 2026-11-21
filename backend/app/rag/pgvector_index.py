"""pgvector-backed index over the ``guideline_chunks`` table (HNSW, cosine distance)."""

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import GuidelineChunkRow
from app.rag.types import Chunk, ScoredChunk


class PgVectorIndex:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._sf = session_factory

    def ids(self) -> set[str]:
        with self._sf() as s:
            return set(s.scalars(select(GuidelineChunkRow.id)))

    def upsert(self, chunks: list[Chunk], vectors: list[list[float]]) -> None:
        if not chunks:
            return
        rows = [
            {
                "id": c.id,
                "source": c.source,
                "section": c.section,
                "title": c.title,
                "content": c.text,
                "embedding": v,
            }
            for c, v in zip(chunks, vectors, strict=True)
        ]
        stmt = insert(GuidelineChunkRow).values(rows)
        stmt = stmt.on_conflict_do_update(
            index_elements=[GuidelineChunkRow.id],
            set_={
                col: stmt.excluded[col]
                for col in ("source", "section", "title", "content", "embedding")
            },
        )
        with self._sf.begin() as s:
            s.execute(stmt)

    def delete(self, ids: set[str]) -> None:
        if ids:
            with self._sf.begin() as s:
                s.execute(delete(GuidelineChunkRow).where(GuidelineChunkRow.id.in_(ids)))

    def search(self, vector: list[float], k: int) -> list[ScoredChunk]:
        distance = GuidelineChunkRow.embedding.cosine_distance(vector)
        stmt = select(GuidelineChunkRow, distance.label("distance")).order_by(distance).limit(k)
        with self._sf() as s:
            return [
                ScoredChunk(
                    chunk=Chunk(
                        id=row.id,
                        source=row.source,
                        section=row.section,
                        title=row.title,
                        text=row.content,
                    ),
                    score=1.0 - float(dist),
                )
                for row, dist in s.execute(stmt)
            ]
