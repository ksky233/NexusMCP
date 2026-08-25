"""InMemory Adapter 对共享 Repository/UoW Contract 的实现。"""

import pytest

from nexusmcp.modules.catalog.adapters.in_memory import InMemoryToolCatalogRepository
from nexusmcp.modules.catalog.adapters.in_memory_uow import InMemoryCatalogUnitOfWorkFactory
from nexusmcp.modules.catalog.ports import CatalogUnitOfWork, ToolCatalogRepository
from nexusmcp.modules.connectors.adapters.in_memory import InMemoryToolBindingRepository
from nexusmcp.modules.connectors.ports import ToolBindingRepository
from tests.contract.repositories.contracts import (
    CatalogRepositoryContract,
    CatalogUnitOfWorkContract,
    ToolBindingRepositoryContract,
    make_published_tool,
)


class TestInMemoryToolCatalogRepository(CatalogRepositoryContract):
    @pytest.fixture
    def empty_catalog(self) -> ToolCatalogRepository:
        return InMemoryToolCatalogRepository()

    @pytest.fixture
    def published_catalog(self) -> ToolCatalogRepository:
        return InMemoryToolCatalogRepository(published_tools=[make_published_tool()])


class TestInMemoryToolBindingRepository(ToolBindingRepositoryContract):
    @pytest.fixture
    def empty_bindings(self) -> ToolBindingRepository:
        return InMemoryToolBindingRepository()


class TestInMemoryCatalogUnitOfWork(CatalogUnitOfWorkContract):
    @pytest.fixture
    def unit_of_work_bundle(
        self,
    ) -> tuple[CatalogUnitOfWork, ToolCatalogRepository, ToolBindingRepository]:
        catalog = InMemoryToolCatalogRepository()
        bindings = InMemoryToolBindingRepository()
        return InMemoryCatalogUnitOfWorkFactory(catalog, bindings)(), catalog, bindings
