"""Integration fixtures: a dedicated ``<db>_test`` database migrated to head.

Run with ``docker compose up -d db`` then ``uv run pytest -m integration``.
"""

from collections.abc import Iterator

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, make_url, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import BACKEND_DIR, get_settings
from app.db.session import create_db_engine, create_session_factory, ping


@pytest.fixture(scope="session")
def test_database_url() -> str:
    url = make_url(get_settings().database_url)
    test_url = url.set(database=f"{url.database}_test")
    admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    if not ping(admin):
        pytest.skip("Postgres is not reachable; run `docker compose up -d db`")
    with admin.connect() as conn:
        exists = conn.scalar(
            text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": test_url.database}
        )
        if not exists:
            conn.execute(text(f'CREATE DATABASE "{test_url.database}"'))
    admin.dispose()
    rendered = test_url.render_as_string(hide_password=False)
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.attributes["configure_logger"] = False
    get_settings.cache_clear()
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("DATABASE_URL", rendered)
        command.upgrade(cfg, "head")
    get_settings.cache_clear()
    return rendered


@pytest.fixture(scope="session")
def engine(test_database_url: str) -> Iterator[Engine]:
    eng = create_db_engine(test_database_url)
    yield eng
    eng.dispose()


@pytest.fixture(scope="session")
def session_factory(engine: Engine) -> sessionmaker[Session]:
    return create_session_factory(engine)
