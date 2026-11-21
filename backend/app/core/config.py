"""Application settings loaded from environment variables (and an optional ``.env`` file)."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_DIR.parent


class Settings(BaseSettings):
    """Typed runtime configuration for the backend."""

    model_config = SettingsConfigDict(
        env_file=(REPO_ROOT / ".env", BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- LLM -------------------------------------------------------------------------------
    groq_api_key: SecretStr | None = None
    groq_model: str = "llama-3.3-70b-versatile"
    llm_temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    llm_timeout_s: float = Field(default=60.0, gt=0)
    llm_max_retries: int = Field(default=3, ge=0, le=10)

    # --- Database --------------------------------------------------------------------------
    database_url: str = "postgresql+psycopg://ark:ark@localhost:5432/ark"

    # --- Agent -----------------------------------------------------------------------------
    max_steps: int = Field(default=8, ge=1, le=25)

    # --- RAG -------------------------------------------------------------------------------
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    embedding_dim: int = 384
    embedding_cache_dir: Path | None = None
    rag_top_k: int = Field(default=3, ge=1, le=10)
    rag_min_score: float = Field(default=0.35, ge=0.0, le=1.0)
    knowledge_dir: Path = BACKEND_DIR / "app" / "knowledge"

    # --- API -------------------------------------------------------------------------------
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:8080"]

    @property
    def psycopg_url(self) -> str:
        """Plain libpq URL (without the SQLAlchemy driver suffix) for LangGraph's Postgres saver."""
        return self.database_url.replace("postgresql+psycopg://", "postgresql://", 1)


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings instance."""
    return Settings()
