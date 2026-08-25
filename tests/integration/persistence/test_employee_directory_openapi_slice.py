"""Employee Directory OpenAPI → PostgreSQL → MCP tools/list 首条纵向切片。"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import httpx2
import pytest
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from nexusmcp.bootstrap.app import create_app
from nexusmcp.bootstrap.config import Settings
from nexusmcp.infrastructure.identifiers import UuidIdentifierGenerator
from nexusmcp.modules.catalog.adapters.sqlalchemy_repository import (
    SqlAlchemyToolCatalogRepository,
)
from nexusmcp.modules.catalog.adapters.sqlalchemy_uow import (
    SqlAlchemyCatalogUnitOfWorkFactory,
)
from nexusmcp.modules.catalog.domain import ToolVersionStatus
from nexusmcp.modules.catalog.publish import PublishTool, PublishToolCommand
from nexusmcp.modules.catalog.review import (
    SubmitToolVersionForReview,
    SubmitToolVersionForReviewCommand,
)
from nexusmcp.modules.connectors.adapters.sqlalchemy_repository import (
    SqlAlchemyToolBindingRepository,
)
from nexusmcp.modules.identity.adapters.sqlalchemy_models import TenantModel
from nexusmcp.modules.openapi_import.adapters.local_document_reader import (
    LocalOpenApiDocumentReader,
)
from nexusmcp.modules.openapi_import.adapters.sqlalchemy_repository import (
    SqlAlchemyOpenApiImportRepository,
)
from nexusmcp.modules.openapi_import.adapters.sqlalchemy_review_uow import (
    SqlAlchemyReviewUnitOfWorkFactory,
)
from nexusmcp.modules.openapi_import.adapters.sqlalchemy_uow import (
    SqlAlchemyOpenApiImportUnitOfWorkFactory,
)
from nexusmcp.modules.openapi_import.domain import ImportJobStatus, OperationReviewStatus
from nexusmcp.modules.openapi_import.import_openapi import ImportOpenApi, ImportOpenApiCommand
from nexusmcp.modules.openapi_import.parser import OpenApiParser
from nexusmcp.modules.openapi_import.review import (
    ReviewImportedOperation,
    ReviewImportedOperationCommand,
)
from nexusmcp.modules.registry.adapters.sqlalchemy_models import UpstreamServiceModel
from nexusmcp.shared.request_context import ProtocolEra, RequestContext
from tests.contract.repositories.contracts import TENANT_A_ID, UPSTREAM_ID

pytestmark = pytest.mark.integration

NOW = datetime(2026, 8, 25, 14, 0, tzinfo=UTC)
UPSTREAM_ROOT = Path(__file__).resolve().parents[3] / "examples" / "upstream_apis"


@dataclass(frozen=True, slots=True)
class FixedClock:
    value: datetime

    def now(self) -> datetime:
        return self.value


def make_context() -> RequestContext:
    return RequestContext(
        request_id="request-employee-directory-slice",
        trace_id="4" * 32,
        protocol_version="2026-07-28",
        protocol_era=ProtocolEra.MODERN,
        tenant_id=TENANT_A_ID,
        principal_id="employee-directory-reviewer",
        authn_method="test",
    )


async def seed_registry(session: AsyncSession) -> None:
    tenant_uuid = uuid.UUID(TENANT_A_ID)
    session.add(
        TenantModel(
            id=tenant_uuid,
            name="Employee Directory Tenant",
            status="active",
        )
    )
    await session.flush()
    session.add(
        UpstreamServiceModel(
            id=uuid.UUID(UPSTREAM_ID),
            tenant_id=tenant_uuid,
            namespace="directory",
            name="employee-directory-api",
            description="Employee Directory Fake API",
            owner="people-platform",
            service_type="http",
            transport_type="http",
            endpoint="http://127.0.0.1:9001",
            auth_scheme="none",
            config_json={},
            status="active",
        )
    )
    await session.commit()


@pytest.mark.asyncio
async def test_employee_directory_openapi_to_mcp_catalog_slice(
    pg_session_factory: async_sessionmaker[AsyncSession],
    migrated_database_url: str,
) -> None:
    async with pg_session_factory() as seed_session:
        await seed_registry(seed_session)

    context = make_context()
    clock = FixedClock(NOW)
    identifier_generator = UuidIdentifierGenerator()
    import_result = await ImportOpenApi(
        SqlAlchemyOpenApiImportUnitOfWorkFactory(pg_session_factory),
        LocalOpenApiDocumentReader(UPSTREAM_ROOT),
        OpenApiParser(),
        clock,
        identifier_generator,
    ).execute(
        ImportOpenApiCommand(
            context=context,
            upstream_service_id=UPSTREAM_ID,
            source_ref="employee_directory/openapi.json",
        )
    )

    async with pg_session_factory() as observer_session:
        imports = SqlAlchemyOpenApiImportRepository(observer_session)
        job = await imports.get_job_by_id(TENANT_A_ID, import_result.import_job_id)
        operations = await imports.list_operations(TENANT_A_ID, import_result.import_job_id)
    assert job is not None and job.status is ImportJobStatus.COMPLETED
    assert len(operations) == 3
    get_employee = next(
        operation for operation in operations if operation.operation_id == "getEmployee"
    )

    review_result = await ReviewImportedOperation(
        SqlAlchemyReviewUnitOfWorkFactory(pg_session_factory),
        clock,
        identifier_generator,
    ).execute(
        ReviewImportedOperationCommand(
            context=context,
            operation_id=get_employee.id,
            owner="people-platform",
        )
    )
    catalog_uow_factory = SqlAlchemyCatalogUnitOfWorkFactory(pg_session_factory)
    await SubmitToolVersionForReview(catalog_uow_factory, clock).execute(
        SubmitToolVersionForReviewCommand(
            context=context,
            tool_version_id=review_result.tool_version_id,
        )
    )

    async with pg_session_factory() as observer_session:
        catalog = SqlAlchemyToolCatalogRepository(observer_session)
        bindings = SqlAlchemyToolBindingRepository(observer_session)
        reviewed = await catalog.get_version_by_id(
            TENANT_A_ID,
            review_result.tool_version_id,
        )
        binding = await bindings.get_by_id(TENANT_A_ID, review_result.tool_binding_id)
        accepted = await SqlAlchemyOpenApiImportRepository(
            observer_session
        ).get_operation_for_update(TENANT_A_ID, get_employee.id)
    assert reviewed is not None and reviewed.status is ToolVersionStatus.REVIEW
    assert binding is not None
    assert accepted is not None and accepted.review_status is OperationReviewStatus.ACCEPTED

    await PublishTool(catalog_uow_factory, clock).execute(
        PublishToolCommand(
            context=context,
            tool_id=review_result.tool_id,
            tool_version_id=reviewed.id,
            expected_schema_digest=reviewed.schema_digest,
            expected_binding_digest=binding.binding_digest,
        )
    )

    app = create_app(
        Settings(
            environment="test",
            catalog_backend="postgresql",
            database_url=SecretStr(migrated_database_url),
            local_tenant_id=TENANT_A_ID,
        )
    )
    async with app.router.lifespan_context(app):
        transport = httpx2.ASGITransport(app=app)
        async with httpx2.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as http_client:
            mcp_transport = streamable_http_client(
                "http://testserver/mcp",
                http_client=http_client,
            )
            async with Client(mcp_transport) as client:
                tools = await client.list_tools(cache_mode="refresh")

    assert [tool.name for tool in tools.tools] == ["directory.get_employee"]
    assert tools.tools[0].input_schema["required"] == ["employee_id"]
    assert tools.tools[0].meta is not None
    assert tools.tools[0].meta["com.nexusmcp/toolVersion"] == 1
