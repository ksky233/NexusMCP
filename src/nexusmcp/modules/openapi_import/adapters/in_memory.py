"""OpenApiImportRepository 的确定性内存 Adapter。"""

from __future__ import annotations

from collections.abc import Iterable

from nexusmcp.modules.openapi_import.domain import ImportedOperation, OpenApiImportJob


class InMemoryOpenApiImportRepository:
    def __init__(
        self,
        jobs: Iterable[OpenApiImportJob] = (),
        operations: Iterable[ImportedOperation] = (),
    ) -> None:
        self._jobs = {job.id: job for job in jobs}
        self._operations = {operation.id: operation for operation in operations}

    async def add_job(self, tenant_id: str, job: OpenApiImportJob) -> None:
        _require_matching_tenant(tenant_id, job.tenant_id)
        if job.id in self._jobs:
            raise ValueError("OpenAPI import job id already exists")
        self._jobs[job.id] = job

    async def save_job(self, tenant_id: str, job: OpenApiImportJob) -> None:
        _require_matching_tenant(tenant_id, job.tenant_id)
        current = self._jobs.get(job.id)
        if current is None or current.tenant_id != tenant_id:
            raise ValueError("OpenAPI import job does not exist in tenant")
        self._jobs[job.id] = job

    async def get_job_by_id(
        self,
        tenant_id: str,
        import_job_id: str,
    ) -> OpenApiImportJob | None:
        job = self._jobs.get(import_job_id)
        return job if job is not None and job.tenant_id == tenant_id else None

    async def get_job_for_update(
        self,
        tenant_id: str,
        import_job_id: str,
    ) -> OpenApiImportJob | None:
        return await self.get_job_by_id(tenant_id, import_job_id)

    async def add_operations(
        self,
        tenant_id: str,
        operations: tuple[ImportedOperation, ...],
    ) -> None:
        existing_keys = {
            (operation.import_job_id, operation.operation_key)
            for operation in self._operations.values()
        }
        for operation in operations:
            _require_matching_tenant(tenant_id, operation.tenant_id)
            if operation.id in self._operations:
                raise ValueError("imported operation id already exists")
            key = (operation.import_job_id, operation.operation_key)
            if key in existing_keys:
                raise ValueError("operation key already exists in import job")
            existing_keys.add(key)
            self._operations[operation.id] = operation

    async def list_operations(
        self,
        tenant_id: str,
        import_job_id: str,
    ) -> tuple[ImportedOperation, ...]:
        operations = (
            operation
            for operation in self._operations.values()
            if operation.tenant_id == tenant_id and operation.import_job_id == import_job_id
        )
        return tuple(sorted(operations, key=lambda operation: operation.operation_key))

    async def get_operation_for_update(
        self,
        tenant_id: str,
        operation_id: str,
    ) -> ImportedOperation | None:
        operation = self._operations.get(operation_id)
        return operation if operation is not None and operation.tenant_id == tenant_id else None

    async def save_operation(
        self,
        tenant_id: str,
        operation: ImportedOperation,
    ) -> None:
        _require_matching_tenant(tenant_id, operation.tenant_id)
        current = self._operations.get(operation.id)
        if current is None or current.tenant_id != tenant_id:
            raise ValueError("imported operation does not exist in tenant")
        self._operations[operation.id] = operation

    def clone(self) -> InMemoryOpenApiImportRepository:
        return InMemoryOpenApiImportRepository(self._jobs.values(), self._operations.values())

    def replace_with(self, repository: InMemoryOpenApiImportRepository) -> None:
        self._jobs = dict(repository._jobs)
        self._operations = dict(repository._operations)


def _require_matching_tenant(requested_tenant_id: str, entity_tenant_id: str) -> None:
    if requested_tenant_id != entity_tenant_id:
        raise ValueError("entity tenant does not match repository tenant scope")
