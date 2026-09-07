"""Imported Operation Direct Publish 的单事务与幂等语义。"""

from collections.abc import Iterator
from datetime import UTC, datetime

import pytest

from nexusmcp.modules.catalog.adapters.in_memory import InMemoryToolCatalogRepository
from nexusmcp.modules.catalog.domain import ToolStatus, ToolVersionStatus
from nexusmcp.modules.connectors.adapters.in_memory import InMemoryToolBindingRepository
from nexusmcp.modules.connectors.domain import ToolBindingStatus
from nexusmcp.modules.openapi_import.adapters.in_memory import InMemoryOpenApiImportRepository
from nexusmcp.modules.openapi_import.adapters.in_memory_review_uow import (
    InMemoryReviewUnitOfWorkFactory,
)
from nexusmcp.modules.openapi_import.direct_publish import (
    DirectPublishImportedOperation,
    DirectPublishImportedOperationCommand,
)
from nexusmcp.modules.openapi_import.domain import (
    ImportedOperation,
    OperationConflictStatus,
    OperationReviewStatus,
)
from nexusmcp.modules.registry.adapters.in_memory import InMemoryUpstreamRepository
from nexusmcp.modules.registry.domain import (
    UpstreamService,
    UpstreamServiceType,
    UpstreamStatus,
)
from nexusmcp.shared.request_context import ActorContext

NOW = datetime(2026, 9, 7, tzinfo=UTC)


class FixedClock:
    def now(self) -> datetime:
        return NOW


class SequenceIdentifierGenerator:
    def __init__(self, *values: str) -> None:
        self._values: Iterator[str] = iter(values)

    def new_id(self) -> str:
        return next(self._values)


def context() -> ActorContext:
    return ActorContext(
        request_id="request-direct-publish",
        trace_id="a" * 32,
        tenant_id="tenant-a",
        principal_id="admin-a",
        authn_method="test",
    )


def operation() -> ImportedOperation:
    return ImportedOperation(
        id="operation-1",
        tenant_id="tenant-a",
        import_job_id="import-1",
        upstream_service_id="upstream-1",
        operation_key="GET /employees/{employee_id}",
        operation_id="getEmployee",
        method="GET",
        path="/employees/{employee_id}",
        normalized_operation={
            "summary": "Get employee",
            "description": "Get one employee by identifier.",
            "tags": ["directory"],
            "parameters": [
                {
                    "argument_name": "employee_id",
                    "upstream_name": "employee_id",
                    "location": "path",
                    "required": True,
                }
            ],
            "request_body": None,
            "side_effect": "read_only",
            "tool_input_schema": {
                "type": "object",
                "properties": {"employee_id": {"type": "string"}},
                "required": ["employee_id"],
                "additionalProperties": False,
            },
            "tool_output_schema": {"type": "object"},
        },
        generated_tool_name="directory.get_employee",
        conflict_status=OperationConflictStatus.NONE,
        review_status=OperationReviewStatus.PENDING,
    )


def upstream() -> UpstreamService:
    return UpstreamService(
        id="upstream-1",
        tenant_id="tenant-a",
        namespace="directory",
        name="employee-directory",
        description=None,
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


@pytest.mark.asyncio
async def test_direct_publish_commits_one_complete_publication_and_replays_idempotently() -> None:
    imports = InMemoryOpenApiImportRepository(operations=(operation(),))
    catalog = InMemoryToolCatalogRepository()
    bindings = InMemoryToolBindingRepository()
    factory = InMemoryReviewUnitOfWorkFactory(
        imports,
        catalog,
        bindings,
        InMemoryUpstreamRepository((upstream(),)),
    )
    use_case = DirectPublishImportedOperation(
        factory,
        FixedClock(),
        SequenceIdentifierGenerator("tool-1", "version-1", "binding-1"),
    )
    command = DirectPublishImportedOperationCommand(
        context=context(),
        operation_id="operation-1",
        owner="people-platform",
        review_notes="direct publish confirmed",
    )

    result = await use_case.execute(command)
    replay = await use_case.execute(command)

    accepted = await imports.get_operation_for_update("tenant-a", "operation-1")
    tool = await catalog.get_tool_by_id("tenant-a", result.tool_id)
    version = await catalog.get_version_by_id("tenant-a", result.tool_version_id)
    binding = await bindings.get_by_id("tenant-a", result.tool_binding_id)
    assert accepted is not None
    assert accepted.review_status is OperationReviewStatus.ACCEPTED
    assert tool is not None and tool.status is ToolStatus.ACTIVE
    assert version is not None and version.status is ToolVersionStatus.PUBLISHED
    assert binding is not None and binding.status is ToolBindingStatus.PUBLISHED
    assert result.already_published is False
    assert replay.already_published is True
    assert replay.tool_version_id == result.tool_version_id
    assert replay.published_at == result.published_at
    assert await catalog.next_version_number("tenant-a", result.tool_id) == 2
