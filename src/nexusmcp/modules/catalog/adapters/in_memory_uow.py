"""Catalog 发布事务的 InMemory Unit of Work Adapter。"""

from __future__ import annotations

from types import TracebackType

from nexusmcp.modules.catalog.adapters.in_memory import InMemoryToolCatalogRepository
from nexusmcp.modules.connectors.adapters.in_memory import InMemoryToolBindingRepository


class InMemoryCatalogUnitOfWork:
    """用事务内副本证明 Commit/Rollback 契约，不伪装数据库细节。"""

    def __init__(
        self,
        catalog: InMemoryToolCatalogRepository | None = None,
        bindings: InMemoryToolBindingRepository | None = None,
    ) -> None:
        self._committed_catalog = (
            catalog if catalog is not None else InMemoryToolCatalogRepository()
        )
        self._committed_bindings = (
            bindings if bindings is not None else InMemoryToolBindingRepository()
        )
        self._transaction_catalog: InMemoryToolCatalogRepository | None = None
        self._transaction_bindings: InMemoryToolBindingRepository | None = None

    @property
    def catalog(self) -> InMemoryToolCatalogRepository:
        if self._transaction_catalog is None:
            raise RuntimeError("unit of work must be entered before accessing repositories")
        return self._transaction_catalog

    @property
    def bindings(self) -> InMemoryToolBindingRepository:
        if self._transaction_bindings is None:
            raise RuntimeError("unit of work must be entered before accessing repositories")
        return self._transaction_bindings

    async def __aenter__(self) -> InMemoryCatalogUnitOfWork:
        if self._transaction_catalog is not None:
            raise RuntimeError("unit of work does not support nested entry")
        self._transaction_catalog = self._committed_catalog.clone()
        self._transaction_bindings = self._committed_bindings.clone()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        # 未显式 Commit 的事务副本直接丢弃，因此正常退出和异常退出都默认回滚。
        self._transaction_catalog = None
        self._transaction_bindings = None

    async def commit(self) -> None:
        catalog = self.catalog
        bindings = self.bindings
        self._committed_catalog.replace_with(catalog)
        self._committed_bindings.replace_with(bindings)

    async def rollback(self) -> None:
        # 回滚后仍允许 Use Case 在同一边界中读取已提交状态，但不会保留之前的修改。
        _ = self.catalog
        _ = self.bindings
        self._transaction_catalog = self._committed_catalog.clone()
        self._transaction_bindings = self._committed_bindings.clone()


class InMemoryCatalogUnitOfWorkFactory:
    """让每次测试 Command 获得独立 UoW，同时共享已提交内存状态。"""

    def __init__(
        self,
        catalog: InMemoryToolCatalogRepository | None = None,
        bindings: InMemoryToolBindingRepository | None = None,
    ) -> None:
        self._catalog = catalog if catalog is not None else InMemoryToolCatalogRepository()
        self._bindings = bindings if bindings is not None else InMemoryToolBindingRepository()

    def __call__(self) -> InMemoryCatalogUnitOfWork:
        return InMemoryCatalogUnitOfWork(self._catalog, self._bindings)
