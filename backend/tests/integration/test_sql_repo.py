import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.db.seed.loader import default_seed
from app.db.seeder import seed_database
from app.repositories.sql_ops import SqlOpsRepository
from tests.contract.ops_repo_contract import OpsRepositoryContract

pytestmark = pytest.mark.integration


class TestSqlOpsRepository(OpsRepositoryContract):
    @pytest.fixture
    def repo(self, session_factory: sessionmaker[Session]) -> SqlOpsRepository:
        repo = SqlOpsRepository(session_factory)
        repo.reset()
        return repo


def test_seed_is_idempotent(session_factory: sessionmaker[Session]) -> None:
    SqlOpsRepository(session_factory).reset()
    with session_factory.begin() as s:
        assert seed_database(s, default_seed()) is False
        assert s.scalar(text("SELECT count(*) FROM routes")) == 6


def test_database_rejects_over_reservation(session_factory: sessionmaker[Session]) -> None:
    SqlOpsRepository(session_factory).reset()
    with pytest.raises(IntegrityError), session_factory.begin() as s:
        s.execute(text("UPDATE stock_items SET reserved = quantity + 1 WHERE depot_id = 'DEP-A'"))
