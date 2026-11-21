import pytest

from app.repositories.memory_ops import InMemoryOpsRepository
from tests.contract.ops_repo_contract import OpsRepositoryContract


class TestInMemoryOpsRepository(OpsRepositoryContract):
    @pytest.fixture
    def repo(self) -> InMemoryOpsRepository:
        return InMemoryOpsRepository()
