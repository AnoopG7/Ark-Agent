"""Long-term operational facts ("Depot B reserved 200 L for Ward 7") on top of a LangGraph store."""

from langgraph.store.base import BaseStore

from app.domain import FactKind, MemoryFact

FACTS_NAMESPACE: tuple[str, ...] = ("ops", "facts")


class FactsService:
    def __init__(self, store: BaseStore, namespace: tuple[str, ...] = FACTS_NAMESPACE) -> None:
        self._store = store
        self._ns = namespace

    def save(self, fact: MemoryFact) -> MemoryFact:
        self._store.put(self._ns, fact.id, fact.model_dump(mode="json"), index=False)
        return fact

    def list(
        self, ward_id: str | None = None, kind: FactKind | None = None, limit: int = 20
    ) -> list[MemoryFact]:
        """Most recent facts first, optionally filtered by ward and kind."""
        flt: dict[str, str] = {}
        if ward_id is not None:
            flt["ward_id"] = ward_id
        if kind is not None:
            flt["kind"] = FactKind(kind).value
        items = self._store.search(self._ns, filter=flt or None, limit=1000)
        facts = [MemoryFact.model_validate(i.value) for i in items]
        facts.sort(key=lambda f: f.created_at, reverse=True)
        return facts[:limit]

    def clear(self) -> int:
        items = self._store.search(self._ns, limit=10_000)
        for item in items:
            self._store.delete(self._ns, item.key)
        return len(items)
