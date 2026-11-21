"""Application wiring: everything the API needs, built once per process."""

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from functools import cached_property
from threading import Lock

from langchain_core.language_models import BaseChatModel
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph.state import CompiledStateGraph
from langgraph.store.base import BaseStore
from sqlalchemy import Engine

from app.agent.graph import build_graph
from app.agent.llm import LLMNotConfiguredError, build_chat_model
from app.core.config import Settings
from app.memory.facts import FactsService
from app.rag.retriever import Retriever
from app.repositories.interfaces import OpsRepository


@dataclass
class AppContainer:
    settings: Settings
    repo: OpsRepository
    checkpointer: BaseCheckpointSaver
    store: BaseStore
    retriever: Retriever | None = None
    llm: BaseChatModel | None = None
    engine: Engine | None = None
    _thread_locks: dict[str, Lock] = field(default_factory=dict)
    _locks_guard: Lock = field(default_factory=Lock)

    @cached_property
    def facts(self) -> FactsService:
        return FactsService(self.store)

    @cached_property
    def graph(self) -> CompiledStateGraph:
        if self.llm is None:
            raise LLMNotConfiguredError("GROQ_API_KEY is not set. Add it to the .env file.")
        return build_graph(
            llm=self.llm,
            repo=self.repo,
            checkpointer=self.checkpointer,
            store=self.store,
            retriever=self.retriever,
            max_steps=self.settings.max_steps,
        )

    def thread_lock(self, thread_id: str) -> Lock:
        """One run at a time per conversation thread."""
        with self._locks_guard:
            return self._thread_locks.setdefault(thread_id, Lock())


@contextmanager
def production_container(settings: Settings) -> Iterator[AppContainer]:
    """Postgres-backed container: migrate, seed, sync the knowledge base, open memory."""
    from alembic import command
    from alembic.config import Config

    from app.core.config import BACKEND_DIR
    from app.db.seed.loader import default_seed
    from app.db.seeder import seed_database
    from app.db.session import create_db_engine, create_session_factory
    from app.memory.factory import open_postgres_backends
    from app.rag.embeddings import FastEmbedEmbedder
    from app.rag.ingest import sync_knowledge
    from app.rag.pgvector_index import PgVectorIndex
    from app.repositories.sql_ops import SqlOpsRepository

    alembic_cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    alembic_cfg.attributes["configure_logger"] = False
    command.upgrade(alembic_cfg, "head")

    engine = create_db_engine(settings.database_url)
    session_factory = create_session_factory(engine)
    with session_factory.begin() as session:
        seed_database(session, default_seed())

    embedder = FastEmbedEmbedder(
        settings.embedding_model, settings.embedding_dim, settings.embedding_cache_dir
    )
    index = PgVectorIndex(session_factory)
    sync_knowledge(settings.knowledge_dir, embedder, index)
    retriever = Retriever(embedder, index, settings.rag_top_k, settings.rag_min_score)

    try:
        llm = build_chat_model(settings)
    except LLMNotConfiguredError:
        llm = None

    try:
        with open_postgres_backends(settings) as memory:
            yield AppContainer(
                settings=settings,
                repo=SqlOpsRepository(session_factory),
                checkpointer=memory.checkpointer,
                store=memory.store,
                retriever=retriever,
                llm=llm,
                engine=engine,
            )
    finally:
        engine.dispose()
