"""Long-term operational memory viewer."""

from fastapi import APIRouter, Query

from app.api.deps import Container
from app.domain import FactKind, MemoryFact

router = APIRouter(prefix="/memory", tags=["memory"])


@router.get("", response_model=list[MemoryFact])
def list_facts(
    c: Container,
    ward_id: str | None = None,
    kind: FactKind | None = None,
    limit: int = Query(default=50, ge=1, le=500),
) -> list[MemoryFact]:
    return c.facts.list(ward_id=ward_id, kind=kind, limit=limit)


@router.delete("")
def clear_facts(c: Container) -> dict[str, int]:
    return {"deleted": c.facts.clear()}
