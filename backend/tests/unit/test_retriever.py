import pytest

from app.core.config import get_settings
from app.rag.embeddings import HashEmbedder
from app.rag.ingest import sync_knowledge
from app.rag.memory_index import InMemoryVectorIndex
from app.rag.retriever import Retriever
from app.tools.executor import run_tool
from app.tools.guidelines import build_guideline_tool


@pytest.fixture
def index() -> InMemoryVectorIndex:
    return InMemoryVectorIndex()


def test_sync_is_idempotent(index: InMemoryVectorIndex) -> None:
    kdir = get_settings().knowledge_dir
    first = sync_knowledge(kdir, HashEmbedder(), index)
    second = sync_knowledge(kdir, HashEmbedder(), index)
    assert first.added > 0 and first.removed == 0
    assert second.added == 0 and second.removed == 0 and second.unchanged == first.added


def test_sync_removes_stale_chunks(index: InMemoryVectorIndex, tmp_path) -> None:
    (tmp_path / "a.md").write_text("# A\n\n## One\nalpha\n\n## Two\nbeta\n")
    sync_knowledge(tmp_path, HashEmbedder(), index)
    (tmp_path / "a.md").write_text("# A\n\n## One\nalpha changed\n")
    stats = sync_knowledge(tmp_path, HashEmbedder(), index)
    assert (stats.added, stats.removed, stats.unchanged) == (1, 2, 0)
    assert len(index.ids()) == 1


def test_water_query_retrieves_water_sop(index: InMemoryVectorIndex) -> None:
    emb = HashEmbedder()
    sync_knowledge(get_settings().knowledge_dir, emb, index)
    hits = Retriever(emb, index, top_k=3, min_score=0.0).search(
        "drinking water litres per person per day"
    )
    assert hits[0].citation == "sop-water-supply.md#daily-allowance"


def test_threshold_filters_irrelevant(index: InMemoryVectorIndex) -> None:
    emb = HashEmbedder()
    sync_knowledge(get_settings().knowledge_dir, emb, index)
    assert Retriever(emb, index, min_score=0.5).search("cryptocurrency exchange rates") == []


def test_guideline_tool(index: InMemoryVectorIndex) -> None:
    emb = HashEmbedder()
    sync_knowledge(get_settings().knowledge_dir, emb, index)
    tool = build_guideline_tool(Retriever(emb, index, min_score=0.0))
    res = run_tool(tool, {"query": "boat capacity litres per trip"})
    assert res.ok
    assert res.data["results"][0]["citation"].startswith("sop-boat-operations.md#")
    assert not run_tool(tool, {"query": "x"}).ok
