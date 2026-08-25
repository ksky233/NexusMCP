"""OpenAPI Import 的 InMemory Unit of Work Adapter。"""

from __future__ import annotations

from types import TracebackType

from nexusmcp.modules.openapi_import.adapters.in_memory import InMemoryOpenApiImportRepository
from nexusmcp.modules.registry.adapters.in_memory import InMemoryUpstreamRepository


class InMemoryOpenApiImportUnitOfWork:
    def __init__(
        self,
        imports: InMemoryOpenApiImportRepository,
        upstreams: InMemoryUpstreamRepository,
    ) -> None:
        self._committed_imports = imports
        self._committed_upstreams = upstreams
        self._transaction_imports: InMemoryOpenApiImportRepository | None = None
        self._transaction_upstreams: InMemoryUpstreamRepository | None = None

    @property
    def imports(self) -> InMemoryOpenApiImportRepository:
        if self._transaction_imports is None:
            raise RuntimeError("unit of work must be entered before accessing repositories")
        return self._transaction_imports

    @property
    def upstreams(self) -> InMemoryUpstreamRepository:
        if self._transaction_upstreams is None:
            raise RuntimeError("unit of work must be entered before accessing repositories")
        return self._transaction_upstreams

    async def __aenter__(self) -> InMemoryOpenApiImportUnitOfWork:
        if self._transaction_imports is not None:
            raise RuntimeError("unit of work does not support nested entry")
        self._transaction_imports = self._committed_imports.clone()
        self._transaction_upstreams = self._committed_upstreams.clone()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self._transaction_imports = None
        self._transaction_upstreams = None

    async def commit(self) -> None:
        self._committed_imports.replace_with(self.imports)
        self._committed_upstreams.replace_with(self.upstreams)

    async def rollback(self) -> None:
        _ = self.imports
        _ = self.upstreams
        self._transaction_imports = self._committed_imports.clone()
        self._transaction_upstreams = self._committed_upstreams.clone()


class InMemoryOpenApiImportUnitOfWorkFactory:
    def __init__(
        self,
        imports: InMemoryOpenApiImportRepository,
        upstreams: InMemoryUpstreamRepository,
    ) -> None:
        self._imports = imports
        self._upstreams = upstreams

    def __call__(self) -> InMemoryOpenApiImportUnitOfWork:
        return InMemoryOpenApiImportUnitOfWork(self._imports, self._upstreams)
