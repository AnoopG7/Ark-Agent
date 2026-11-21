"""Idempotent ingestion of the Markdown knowledge base into a vector index."""

from pathlib import Path

from app.rag.chunker import chunk_markdown
from app.rag.embeddings import Embedder
from app.rag.index import VectorIndex
from app.rag.types import Chunk, SyncStats


def load_chunks(knowledge_dir: Path) -> list[Chunk]:
    chunks: list[Chunk] = []
    for path in sorted(knowledge_dir.glob("*.md")):
        chunks.extend(chunk_markdown(path.read_text(encoding="utf-8"), source=path.name))
    return chunks


def sync_knowledge(knowledge_dir: Path, embedder: Embedder, index: VectorIndex) -> SyncStats:
    """Make the index match ``knowledge_dir``.

    Chunk ids are content hashes, so unchanged chunks are skipped (no re-embedding), edited chunks
    get new ids and are added, and chunks that no longer exist are removed. Running it twice in a
    row adds nothing the second time.
    """
    chunks = load_chunks(knowledge_dir)
    wanted = {c.id: c for c in chunks}
    existing = index.ids()
    new = [wanted[i] for i in wanted.keys() - existing]
    stale = existing - wanted.keys()
    if new:
        index.upsert(new, embedder.embed_documents([f"{c.title}\n{c.text}" for c in new]))
    index.delete(stale)
    return SyncStats(added=len(new), removed=len(stale), unchanged=len(wanted) - len(new))
