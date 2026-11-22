import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MAX_STEPS", raising=False)
    s = Settings(_env_file=None)
    assert s.groq_model == "openai/gpt-oss-120b"
    assert s.max_steps == 8
    assert s.embedding_dim == 384
    assert s.groq_api_key is None


def test_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MAX_STEPS", "3")
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test")
    s = Settings(_env_file=None)
    assert s.max_steps == 3
    assert s.groq_api_key is not None
    assert s.groq_api_key.get_secret_value() == "gsk_test"
    assert "gsk_test" not in repr(s)


def test_invalid_max_steps_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MAX_STEPS", "0")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_psycopg_url_strips_sqlalchemy_driver() -> None:
    s = Settings(_env_file=None, database_url="postgresql+psycopg://u:p@h:5432/d")
    assert s.psycopg_url == "postgresql://u:p@h:5432/d"


def test_reasoning_effort_defaults_low_and_blank_disables(monkeypatch) -> None:
    from app.core.config import Settings

    assert Settings(_env_file=None).llm_reasoning_effort == "low"
    monkeypatch.setenv("LLM_REASONING_EFFORT", "")
    assert Settings(_env_file=None).llm_reasoning_effort is None
