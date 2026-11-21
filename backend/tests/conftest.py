"""Shared pytest fixtures for the Ark-Agent backend."""

import pytest


@pytest.fixture(scope="session")
def retriever_for_eval():
    from app.core.config import get_settings
    from app.rag.embeddings import HashEmbedder
    from app.rag.ingest import sync_knowledge
    from app.rag.memory_index import InMemoryVectorIndex
    from app.rag.retriever import Retriever

    index = InMemoryVectorIndex()
    sync_knowledge(get_settings().knowledge_dir, HashEmbedder(), index)
    return Retriever(HashEmbedder(), index, min_score=0.0)
