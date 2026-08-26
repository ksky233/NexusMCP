"""OpenAPI Import 状态读取的 Application Query。"""

from dataclasses import dataclass

from nexusmcp.modules.openapi_import.domain import ImportedOperation, OpenApiImportJob
from nexusmcp.modules.openapi_import.ports import OpenApiImportUnitOfWorkFactory
from nexusmcp.shared.errors import OpenApiImportJobNotFoundError
from nexusmcp.shared.request_context import ActorContext


@dataclass(frozen=True, slots=True)
class GetOpenApiImportQuery:
    context: ActorContext
    import_job_id: str


@dataclass(frozen=True, slots=True)
class GetOpenApiImportResult:
    job: OpenApiImportJob
    operations: tuple[ImportedOperation, ...]


class GetOpenApiImport:
    def __init__(self, unit_of_work_factory: OpenApiImportUnitOfWorkFactory) -> None:
        self._unit_of_work_factory = unit_of_work_factory

    async def execute(self, query: GetOpenApiImportQuery) -> GetOpenApiImportResult:
        async with self._unit_of_work_factory() as unit_of_work:
            job = await unit_of_work.imports.get_job_by_id(
                query.context.tenant_id,
                query.import_job_id,
            )
            if job is None:
                raise OpenApiImportJobNotFoundError(
                    f"import job {query.import_job_id} was not found in tenant"
                )
            operations = await unit_of_work.imports.list_operations(
                query.context.tenant_id,
                query.import_job_id,
            )
            return GetOpenApiImportResult(job=job, operations=operations)
