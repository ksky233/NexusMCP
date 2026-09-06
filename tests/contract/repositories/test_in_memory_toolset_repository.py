"""InMemory Toolset Adapter 对共享 Repository/UoW Contract 的实现。"""

import pytest

from nexusmcp.modules.toolsets.adapters.in_memory import InMemoryToolsetRepository
from nexusmcp.modules.toolsets.adapters.in_memory_uow import InMemoryToolsetUnitOfWorkFactory
from nexusmcp.modules.toolsets.ports import ToolsetRepository, ToolsetUnitOfWork
from tests.contract.repositories.toolset_contracts import (
    ToolsetRepositoryContract,
    ToolsetUnitOfWorkContract,
)


class TestInMemoryToolsetRepository(ToolsetRepositoryContract):
    @pytest.fixture
    def empty_toolsets(self) -> ToolsetRepository:
        return InMemoryToolsetRepository()


class TestInMemoryToolsetUnitOfWork(ToolsetUnitOfWorkContract):
    @pytest.fixture
    def unit_of_work_bundle(self) -> tuple[ToolsetUnitOfWork, ToolsetRepository]:
        repository = InMemoryToolsetRepository()
        return InMemoryToolsetUnitOfWorkFactory(toolsets=repository)(), repository
