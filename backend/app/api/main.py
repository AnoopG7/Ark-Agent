"""FastAPI application factory.

uv run uvicorn app.api.main:app --reload
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.container import AppContainer, production_container
from app.api.routers import memory, ops, system, threads
from app.core.config import get_settings


def create_app(container: AppContainer | None = None) -> FastAPI:
    """Build the app. Tests pass a ready container; otherwise Postgres wiring runs on startup."""
    settings = container.settings if container else get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if container is not None:
            app.state.container = container
            yield
            return
        with production_container(settings) as built:
            app.state.container = built
            yield

    app = FastAPI(
        title="Ark-Agent API",
        description="Driftwood Bay flood-relief planning agent (ReAct + LangGraph + RAG).",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    for module in (system, threads, ops, memory):
        app.include_router(module.router, prefix="/api")
    return app


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
app = create_app()
