"""Health, graph diagram and knowledge-base search."""

from fastapi import APIRouter, HTTPException, Query, status

from app.agent.diagram import graph_mermaid
from app.api.deps import Container
from app.api.schemas import HealthResponse, KnowledgeHit
from app.db.session import ping

router = APIRouter(tags=["system"])


@router.get("/health", response_model=HealthResponse)
def health(c: Container) -> HealthResponse:
    database = ping(c.engine) if c.engine is not None else True
    return HealthResponse(
        status="ok" if database else "degraded",
        database=database,
        llm_configured=c.llm is not None,
        model=c.settings.groq_model,
    )


@router.get("/graph")
def graph() -> dict[str, str]:
    return {"mermaid": graph_mermaid()}


@router.get("/knowledge/search", response_model=list[KnowledgeHit])
def search_knowledge(
    c: Container, q: str = Query(min_length=3, max_length=300), k: int = Query(3, ge=1, le=10)
) -> list[KnowledgeHit]:
    if c.retriever is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Knowledge base not loaded.")
    return [KnowledgeHit(**h.model_dump()) for h in c.retriever.search(q, k)]
