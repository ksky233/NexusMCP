"""ImportedOperation Review 跨上下文事务 Port。"""

from types import TracebackType
from typing import Protocol, Self

from nexusmcp.modules.catalog.ports import ToolCatalogRepository
from nexusmcp.modules.connectors.ports import ToolBindingRepository
from nexusmcp.modules.openapi_import.ports import OpenApiImportRepository
from nexusmcp.modules.registry.ports import UpstreamRepository


class ReviewUnitOfWork(Protocol):
    @property
    def imports(self) -> OpenApiImportRepository: ...

    @property
    def catalog(self) -> ToolCatalogRepository: ...

    @property
    def bindings(self) -> ToolBindingRepository: ...

    @property
    def upstreams(self) -> UpstreamRepository: ...

    async def __aenter__(self) -> Self: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...


class ReviewUnitOfWorkFactory(Protocol):
    def __call__(self) -> ReviewUnitOfWork: ...
