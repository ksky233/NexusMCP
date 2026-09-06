"""Toolset Aggregate 的 InMemory Unit of Work。"""

from __future__ import annotations

from types import TracebackType

from nexusmcp.modules.toolsets.adapters.in_memory import (
    InMemoryToolsetCatalogReader,
    InMemoryToolsetRepository,
)


class InMemoryToolsetUnitOfWork:
    def __init__(
        self,
        toolsets: InMemoryToolsetRepository,
        catalog: InMemoryToolsetCatalogReader,
    ) -> None:
        self._committed_toolsets = toolsets
        self._catalog = catalog
        self._transaction_toolsets: InMemoryToolsetRepository | None = None

    @property
    def toolsets(self) -> InMemoryToolsetRepository:
        if self._transaction_toolsets is None:
            raise RuntimeError("unit of work must be entered before accessing repositories")
        return self._transaction_toolsets

    @property
    def catalog(self) -> InMemoryToolsetCatalogReader:
        if self._transaction_toolsets is None:
            raise RuntimeError("unit of work must be entered before accessing repositories")
        return self._catalog

    async def __aenter__(self) -> InMemoryToolsetUnitOfWork:
        if self._transaction_toolsets is not None:
            raise RuntimeError("unit of work does not support nested entry")
        self._transaction_toolsets = self._committed_toolsets.clone()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self._transaction_toolsets = None

    async def commit(self) -> None:
        self._committed_toolsets.replace_with(self.toolsets)

    async def rollback(self) -> None:
        _ = self.toolsets
        self._transaction_toolsets = self._committed_toolsets.clone()


class InMemoryToolsetUnitOfWorkFactory:
    def __init__(
        self,
        toolsets: InMemoryToolsetRepository | None = None,
        catalog: InMemoryToolsetCatalogReader | None = None,
    ) -> None:
        self._toolsets = toolsets if toolsets is not None else InMemoryToolsetRepository()
        self._catalog = catalog if catalog is not None else InMemoryToolsetCatalogReader()

    def __call__(self) -> InMemoryToolsetUnitOfWork:
        return InMemoryToolsetUnitOfWork(self._toolsets, self._catalog)
