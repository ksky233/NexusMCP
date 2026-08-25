"""ImportedOperation Review 的 InMemory Unit of Work。"""

from __future__ import annotations

from types import TracebackType

from nexusmcp.modules.catalog.adapters.in_memory import InMemoryToolCatalogRepository
from nexusmcp.modules.connectors.adapters.in_memory import InMemoryToolBindingRepository
from nexusmcp.modules.openapi_import.adapters.in_memory import InMemoryOpenApiImportRepository
from nexusmcp.modules.registry.adapters.in_memory import InMemoryUpstreamRepository


class InMemoryReviewUnitOfWork:
    def __init__(
        self,
        imports: InMemoryOpenApiImportRepository,
        catalog: InMemoryToolCatalogRepository,
        bindings: InMemoryToolBindingRepository,
        upstreams: InMemoryUpstreamRepository,
    ) -> None:
        self._committed_imports = imports
        self._committed_catalog = catalog
        self._committed_bindings = bindings
        self._committed_upstreams = upstreams
        self._transaction_imports: InMemoryOpenApiImportRepository | None = None
        self._transaction_catalog: InMemoryToolCatalogRepository | None = None
        self._transaction_bindings: InMemoryToolBindingRepository | None = None
        self._transaction_upstreams: InMemoryUpstreamRepository | None = None

    @property
    def imports(self) -> InMemoryOpenApiImportRepository:
        return self._require(self._transaction_imports)

    @property
    def catalog(self) -> InMemoryToolCatalogRepository:
        return self._require(self._transaction_catalog)

    @property
    def bindings(self) -> InMemoryToolBindingRepository:
        return self._require(self._transaction_bindings)

    @property
    def upstreams(self) -> InMemoryUpstreamRepository:
        return self._require(self._transaction_upstreams)

    async def __aenter__(self) -> InMemoryReviewUnitOfWork:
        if self._transaction_imports is not None:
            raise RuntimeError("unit of work does not support nested entry")
        self._transaction_imports = self._committed_imports.clone()
        self._transaction_catalog = self._committed_catalog.clone()
        self._transaction_bindings = self._committed_bindings.clone()
        self._transaction_upstreams = self._committed_upstreams.clone()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self._transaction_imports = None
        self._transaction_catalog = None
        self._transaction_bindings = None
        self._transaction_upstreams = None

    async def commit(self) -> None:
        self._committed_imports.replace_with(self.imports)
        self._committed_catalog.replace_with(self.catalog)
        self._committed_bindings.replace_with(self.bindings)
        self._committed_upstreams.replace_with(self.upstreams)

    async def rollback(self) -> None:
        _ = self.imports
        self._transaction_imports = self._committed_imports.clone()
        self._transaction_catalog = self._committed_catalog.clone()
        self._transaction_bindings = self._committed_bindings.clone()
        self._transaction_upstreams = self._committed_upstreams.clone()

    @staticmethod
    def _require[T](value: T | None) -> T:
        if value is None:
            raise RuntimeError("unit of work must be entered before accessing repositories")
        return value


class InMemoryReviewUnitOfWorkFactory:
    def __init__(
        self,
        imports: InMemoryOpenApiImportRepository,
        catalog: InMemoryToolCatalogRepository,
        bindings: InMemoryToolBindingRepository,
        upstreams: InMemoryUpstreamRepository,
    ) -> None:
        self._imports = imports
        self._catalog = catalog
        self._bindings = bindings
        self._upstreams = upstreams

    def __call__(self) -> InMemoryReviewUnitOfWork:
        return InMemoryReviewUnitOfWork(
            self._imports,
            self._catalog,
            self._bindings,
            self._upstreams,
        )
