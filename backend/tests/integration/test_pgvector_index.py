import pytest
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.rag.embeddings import HashEmbedder
from app.rag.ingest import sync_knowledge
from app.rag.pgvector_index import PgVectorIndex
from app.rag.retriever import Retriever

pytestmark = pytest.mark.integration


def test_pgvector_sync_and_search(session_factory: sessionmaker[Session]) -> None:
    index = PgVectorIndex(session_factory)
    index.delete(index.ids())
    emb = HashEmbedder()
    first = sync_knowledge(get_settings().knowledge_dir, emb, index)
    second = sync_knowledge(get_settings().knowledge_dir, emb, index)
    assert first.added > 0 and second.added == 0 and second.unchanged == first.added
    hits = Retriever(emb, index, min_score=0.0).search("drinking water litres per person per day")
    assert hits[0].citation == "sop-water-supply.md#daily-allowance"
    assert 0.0 < hits[0].score <= 1.0
