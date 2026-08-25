"""OpenAPI Import → Operation Review → Tool Review → Publish 编排测试。"""

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pytest

from nexusmcp.modules.catalog.adapters.in_memory import InMemoryToolCatalogRepository
from nexusmcp.modules.catalog.adapters.in_memory_uow import InMemoryCatalogUnitOfWorkFactory
from nexusmcp.modules.catalog.domain import ToolStatus, ToolVersionStatus
from nexusmcp.modules.catalog.publish import PublishTool, PublishToolCommand
from nexusmcp.modules.catalog.review import (
    SubmitToolVersionForReview,
    SubmitToolVersionForReviewCommand,
)
from nexusmcp.modules.connectors.adapters.in_memory import InMemoryToolBindingRepository
from nexusmcp.modules.connectors.domain import ToolBindingStatus
from nexusmcp.modules.openapi_import.adapters.in_memory import InMemoryOpenApiImportRepository
from nexusmcp.modules.openapi_import.adapters.in_memory_review_uow import (
    InMemoryReviewUnitOfWorkFactory,
)
from nexusmcp.modules.openapi_import.adapters.in_memory_uow import (
    InMemoryOpenApiImportUnitOfWorkFactory,
)
from nexusmcp.modules.openapi_import.adapters.local_document_reader import (
    LocalOpenApiDocumentReader,
)
from nexusmcp.modules.openapi_import.domain import (
    ImportJobStatus,
    OpenApiDocument,
    OperationReviewStatus,
)
from nexusmcp.modules.openapi_import.import_openapi import ImportOpenApi, ImportOpenApiCommand
from nexusmcp.modules.openapi_import.parser import OpenApiParser
from nexusmcp.modules.openapi_import.review import (
    ReviewImportedOperation,
    ReviewImportedOperationCommand,
)
from nexusmcp.modules.openapi_import.source_ports import OpenApiDocumentReader
from nexusmcp.modules.registry.adapters.in_memory import InMemoryUpstreamRepository
from nexusmcp.modules.registry.domain import (
    UpstreamService,
    UpstreamServiceType,
    UpstreamStatus,
)
from nexusmcp.shared.errors import OpenApiFeatureUnsupportedError
from nexusmcp.shared.request_context import ProtocolEra, RequestContext

NOW = datetime(2026, 8, 25, 13, 0, tzinfo=UTC)
UPSTREAM_ROOT = Path(__file__).resolve().parents[4] / "examples" / "upstream_apis"


@dataclass(frozen=True, slots=True)
class FixedClock:
    value: datetime

    def now(self) -> datetime:
        return self.value


class SequenceIdentifierGenerator:
    def __init__(self, *values: str) -> None:
        self._values = iter(values)

    def new_id(self) -> str:
        return next(self._values)


class StaticDocumentReader:
    def __init__(self, document: OpenApiDocument) -> None:
        self._document = document

    async def read(self, source_ref: str) -> OpenApiDocument:
        _ = source_ref
        return self._document


def _context() -> RequestContext:
    return RequestContext(
        request_id="request-import-review",
        trace_id="3" * 32,
        protocol_version="2026-07-28",
        protocol_era=ProtocolEra.MODERN,
        tenant_id="tenant-a",
        principal_id="reviewer-a",
        authn_method="test",
    )


def _upstream() -> UpstreamService:
    return UpstreamService(
        id="upstream-a",
        tenant_id="tenant-a",
        namespace="directory",
        name="employee-directory",
        description="Employee directory",
        owner="people-platform",
        service_type=UpstreamServiceType.HTTP,
        transport_type="http",
        endpoint="http://127.0.0.1:9001",
        protocol_min=None,
        protocol_max=None,
        auth_scheme="none",
        config={},
        status=UpstreamStatus.ACTIVE,
    )


def _import_use_case(
    imports: InMemoryOpenApiImportRepository,
    upstreams: InMemoryUpstreamRepository,
    reader: OpenApiDocumentReader,
    identifier_generator: SequenceIdentifierGenerator,
) -> ImportOpenApi:
    return ImportOpenApi(
        InMemoryOpenApiImportUnitOfWorkFactory(imports, upstreams),
        reader,
        OpenApiParser(),
        FixedClock(NOW),
        identifier_generator,
    )


@pytest.mark.asyncio
async def test_employee_directory_import_review_and_publish_pipeline() -> None:
    imports = InMemoryOpenApiImportRepository()
    upstreams = InMemoryUpstreamRepository([_upstream()])
    catalog = InMemoryToolCatalogRepository()
    bindings = InMemoryToolBindingRepository()
    context = _context()
    import_use_case = _import_use_case(
        imports,
        upstreams,
        LocalOpenApiDocumentReader(UPSTREAM_ROOT),
        SequenceIdentifierGenerator("job-1", "operation-1", "operation-2", "operation-3"),
    )

    import_result = await import_use_case.execute(
        ImportOpenApiCommand(
            context=context,
            upstream_service_id="upstream-a",
            source_ref="employee_directory/openapi.json",
        )
    )
    job = await imports.get_job_by_id("tenant-a", import_result.import_job_id)
    operations = await imports.list_operations("tenant-a", import_result.import_job_id)

    assert job is not None and job.status is ImportJobStatus.COMPLETED
    assert len(operations) == 3
    assert import_result.conflict_count == 0
    get_employee = next(
        operation for operation in operations if operation.operation_id == "getEmployee"
    )

    review_use_case = ReviewImportedOperation(
        InMemoryReviewUnitOfWorkFactory(imports, catalog, bindings, upstreams),
        FixedClock(NOW),
        SequenceIdentifierGenerator("tool-1", "version-1", "binding-1"),
    )
    review_result = await review_use_case.execute(
        ReviewImportedOperationCommand(
            context=context,
            operation_id=get_employee.id,
            owner="people-platform",
        )
    )
    repeated_review = await review_use_case.execute(
        ReviewImportedOperationCommand(
            context=context,
            operation_id=get_employee.id,
            owner="people-platform",
        )
    )

    accepted = await imports.get_operation_for_update("tenant-a", get_employee.id)
    draft = await catalog.get_version_by_id("tenant-a", review_result.tool_version_id)
    binding = await bindings.get_by_id("tenant-a", review_result.tool_binding_id)
    tool = await catalog.get_tool_by_id("tenant-a", review_result.tool_id)
    assert accepted is not None and accepted.review_status is OperationReviewStatus.ACCEPTED
    assert draft is not None and draft.status is ToolVersionStatus.DRAFT
    assert binding is not None and binding.status is ToolBindingStatus.DRAFT
    assert tool is not None and tool.status is ToolStatus.DISABLED
    assert review_result.canonical_name == "directory.get_employee"
    assert repeated_review == review_result
    assert draft.input_schema["required"] == ["employee_id"]
    assert binding.binding_config["path_template"] == "/employees/{employee_id}"

    catalog_uow_factory = InMemoryCatalogUnitOfWorkFactory(catalog, bindings, upstreams)
    await SubmitToolVersionForReview(catalog_uow_factory, FixedClock(NOW)).execute(
        SubmitToolVersionForReviewCommand(
            context=context,
            tool_version_id=draft.id,
        )
    )
    reviewed = await catalog.get_version_by_id("tenant-a", draft.id)
    assert reviewed is not None and reviewed.status is ToolVersionStatus.REVIEW

    await PublishTool(catalog_uow_factory, FixedClock(NOW)).execute(
        PublishToolCommand(
            context=context,
            tool_id=tool.id,
            tool_version_id=reviewed.id,
            expected_schema_digest=reviewed.schema_digest,
            expected_binding_digest=binding.binding_digest,
        )
    )

    published = await catalog.get_version_by_id("tenant-a", reviewed.id)
    published_binding = await bindings.get_by_id("tenant-a", binding.id)
    active_tool = await catalog.get_tool_by_id("tenant-a", tool.id)
    assert published is not None and published.status is ToolVersionStatus.PUBLISHED
    assert published_binding is not None
    assert published_binding.status is ToolBindingStatus.PUBLISHED
    assert active_tool is not None and active_tool.status is ToolStatus.ACTIVE


@pytest.mark.asyncio
async def test_parser_failure_is_persisted_as_safe_failed_job() -> None:
    imports = InMemoryOpenApiImportRepository()
    upstreams = InMemoryUpstreamRepository([_upstream()])
    invalid_document = OpenApiDocument(
        source_ref="invalid.json",
        source_digest="0" * 64,
        content={"openapi": "2.0", "paths": {}},
    )
    use_case = _import_use_case(
        imports,
        upstreams,
        StaticDocumentReader(invalid_document),
        SequenceIdentifierGenerator("job-failed"),
    )

    with pytest.raises(OpenApiFeatureUnsupportedError):
        await use_case.execute(
            ImportOpenApiCommand(
                context=_context(),
                upstream_service_id="upstream-a",
                source_ref="invalid.json",
            )
        )

    failed = await imports.get_job_by_id("tenant-a", "job-failed")
    assert failed is not None and failed.status is ImportJobStatus.FAILED
    assert failed.error_summary == OpenApiFeatureUnsupportedError.safe_message
