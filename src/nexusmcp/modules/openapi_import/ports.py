"""OpenAPI Import 状态持久化与事务 Port。"""

from types import TracebackType
from typing import Protocol, Self

from nexusmcp.modules.openapi_import.domain import ImportedOperation, OpenApiImportJob
from nexusmcp.modules.registry.ports import UpstreamRepository


class OpenApiImportRepository(Protocol):
    async def add_job(self, tenant_id: str, job: OpenApiImportJob) -> None: ...

    async def save_job(self, tenant_id: str, job: OpenApiImportJob) -> None: ...

    async def get_job_by_id(
        self,
        tenant_id: str,
        import_job_id: str,
    ) -> OpenApiImportJob | None: ...

    async def get_job_for_update(
        self,
        tenant_id: str,
        import_job_id: str,
    ) -> OpenApiImportJob | None: ...

    async def add_operations(
        self,
        tenant_id: str,
        operations: tuple[ImportedOperation, ...],
    ) -> None: ...

    async def list_operations(
        self,
        tenant_id: str,
        import_job_id: str,
    ) -> tuple[ImportedOperation, ...]: ...

    async def get_operation_for_update(
        self,
        tenant_id: str,
        operation_id: str,
    ) -> ImportedOperation | None: ...

    async def save_operation(
        self,
        tenant_id: str,
        operation: ImportedOperation,
    ) -> None: ...


class OpenApiImportUnitOfWork(Protocol):
    @property
    def imports(self) -> OpenApiImportRepository: ...

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


class OpenApiImportUnitOfWorkFactory(Protocol):
    def __call__(self) -> OpenApiImportUnitOfWork: ...
