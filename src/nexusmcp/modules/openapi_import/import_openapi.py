"""Local OpenAPI Fixture 导入的 Application Use Case。"""

from dataclasses import dataclass

from nexusmcp.modules.openapi_import.domain import (
    ImportedOperation,
    ImportJobStatus,
    OpenApiImportJob,
    OpenApiSourceType,
    OperationReviewStatus,
    ParsedOpenApiDocument,
)
from nexusmcp.modules.openapi_import.parser import OpenApiParser
from nexusmcp.modules.openapi_import.ports import OpenApiImportUnitOfWorkFactory
from nexusmcp.modules.openapi_import.source_ports import OpenApiDocumentReader
from nexusmcp.modules.registry.domain import UpstreamStatus
from nexusmcp.shared.clock import Clock
from nexusmcp.shared.errors import (
    NexusMcpError,
    OpenApiDocumentInvalidError,
    TenantBoundaryViolationError,
    UpstreamNotActiveError,
)
from nexusmcp.shared.identifiers import IdentifierGenerator
from nexusmcp.shared.request_context import RequestContext


@dataclass(frozen=True, slots=True)
class ImportOpenApiCommand:
    context: RequestContext
    upstream_service_id: str
    source_ref: str
    operation_allowlist: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ImportOpenApiResult:
    import_job_id: str
    operation_ids: tuple[str, ...]
    conflict_count: int


class ImportOpenApi:
    def __init__(
        self,
        unit_of_work_factory: OpenApiImportUnitOfWorkFactory,
        document_reader: OpenApiDocumentReader,
        parser: OpenApiParser,
        clock: Clock,
        identifier_generator: IdentifierGenerator,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._document_reader = document_reader
        self._parser = parser
        self._clock = clock
        self._identifier_generator = identifier_generator

    async def execute(self, command: ImportOpenApiCommand) -> ImportOpenApiResult:
        """读取在事务外进行；Job 状态和 Operation 使用多个短事务持久化。"""

        document = await self._document_reader.read(command.source_ref)
        tenant_id = command.context.tenant_id
        job_id = self._identifier_generator.new_id()
        created_at = self._clock.now()

        async with self._unit_of_work_factory() as unit_of_work:
            upstream = await unit_of_work.upstreams.get_for_update(
                tenant_id,
                command.upstream_service_id,
            )
            if upstream is None:
                raise TenantBoundaryViolationError(
                    "OpenAPI upstream was not found in the requested tenant"
                )
            if upstream.status is not UpstreamStatus.ACTIVE:
                raise UpstreamNotActiveError(f"upstream {upstream.id} is not active")
            job = OpenApiImportJob(
                id=job_id,
                tenant_id=tenant_id,
                upstream_service_id=upstream.id,
                source_type=OpenApiSourceType.LOCAL_FIXTURE,
                source_ref=document.source_ref,
                source_digest=document.source_digest,
                openapi_version=None,
                operation_allowlist=command.operation_allowlist,
                allowlist_snapshot={"network_access": False, "source_type": "local_fixture"},
                status=ImportJobStatus.PENDING,
                error_summary=None,
                created_by=command.context.principal_id,
                created_at=created_at,
            ).start_validation(created_at)
            await unit_of_work.imports.add_job(tenant_id, job)
            await unit_of_work.commit()

        try:
            await self._mark_parsing(tenant_id, job_id)
            parsed = self._parser.parse(
                document.content,
                namespace=upstream.namespace,
                operation_allowlist=command.operation_allowlist,
            )
            operations = self._build_operations(tenant_id, job, parsed)
            await self._complete_job(tenant_id, job_id, parsed, operations)
        except NexusMcpError as error:
            await self._fail_job(tenant_id, job_id, error.safe_message)
            raise
        except Exception as error:
            await self._fail_job(
                tenant_id,
                job_id,
                OpenApiDocumentInvalidError.safe_message,
            )
            raise OpenApiDocumentInvalidError("unexpected OpenAPI parser failure") from error

        return ImportOpenApiResult(
            import_job_id=job_id,
            operation_ids=tuple(operation.id for operation in operations),
            conflict_count=sum(
                operation.conflict_status.value != "none" for operation in operations
            ),
        )

    async def _mark_parsing(self, tenant_id: str, job_id: str) -> None:
        async with self._unit_of_work_factory() as unit_of_work:
            job = await unit_of_work.imports.get_job_for_update(tenant_id, job_id)
            if job is None:
                raise OpenApiDocumentInvalidError("import job disappeared before parsing")
            await unit_of_work.imports.save_job(tenant_id, job.start_parsing())
            await unit_of_work.commit()

    def _build_operations(
        self,
        tenant_id: str,
        job: OpenApiImportJob,
        parsed: ParsedOpenApiDocument,
    ) -> tuple[ImportedOperation, ...]:
        return tuple(
            ImportedOperation(
                id=self._identifier_generator.new_id(),
                tenant_id=tenant_id,
                import_job_id=job.id,
                upstream_service_id=job.upstream_service_id,
                operation_key=operation.operation_key,
                operation_id=operation.operation_id,
                method=operation.method,
                path=operation.path,
                normalized_operation=operation.normalized_operation,
                generated_tool_name=operation.generated_tool_name,
                conflict_status=operation.conflict_status,
                review_status=OperationReviewStatus.PENDING,
            )
            for operation in parsed.operations
        )

    async def _complete_job(
        self,
        tenant_id: str,
        job_id: str,
        parsed: ParsedOpenApiDocument,
        operations: tuple[ImportedOperation, ...],
    ) -> None:
        async with self._unit_of_work_factory() as unit_of_work:
            job = await unit_of_work.imports.get_job_for_update(tenant_id, job_id)
            if job is None:
                raise OpenApiDocumentInvalidError("import job disappeared before completion")
            await unit_of_work.imports.add_operations(tenant_id, operations)
            await unit_of_work.imports.save_job(
                tenant_id,
                job.complete(parsed.openapi_version, self._clock.now()),
            )
            await unit_of_work.commit()

    async def _fail_job(self, tenant_id: str, job_id: str, safe_summary: str) -> None:
        async with self._unit_of_work_factory() as unit_of_work:
            job = await unit_of_work.imports.get_job_for_update(tenant_id, job_id)
            if job is None or job.status in (ImportJobStatus.COMPLETED, ImportJobStatus.FAILED):
                return
            await unit_of_work.imports.save_job(
                tenant_id,
                job.fail(safe_summary, self._clock.now()),
            )
            await unit_of_work.commit()
