"""三个业务场景复用同一 OpenAPI Pipeline 的 PostgreSQL/MCP 通用性证据。"""

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
from nexusmcp.modules.catalog.domain import ToolSideEffect, ToolVersion
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
from nexusmcp.modules.openapi_import.domain import OperationConflictStatus
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

NOW = datetime(2026, 8, 25, 15, 0, tzinfo=UTC)
UPSTREAM_ROOT = Path(__file__).resolve().parents[3] / "examples" / "upstream_apis"
OPS_UPSTREAM_ID = "00000000-0000-0000-0000-000000000402"
INVENTORY_UPSTREAM_ID = "00000000-0000-0000-0000-000000000403"


@dataclass(frozen=True, slots=True)
class FixedClock:
    value: datetime

    def now(self) -> datetime:
        return self.value


@dataclass(frozen=True, slots=True)
class Scenario:
    namespace: str
    name: str
    source_ref: str
    upstream_id: str
    endpoint: str


SCENARIOS = (
    Scenario(
        namespace="directory",
        name="employee-directory-api",
        source_ref="employee_directory/openapi.json",
        upstream_id=UPSTREAM_ID,
        endpoint="http://127.0.0.1:9001",
    ),
    Scenario(
        namespace="ops",
        name="it-operations-api",
        source_ref="operations/openapi.json",
        upstream_id=OPS_UPSTREAM_ID,
        endpoint="http://127.0.0.1:9002",
    ),
    Scenario(
        namespace="inventory",
        name="inventory-api",
        source_ref="inventory/openapi.json",
        upstream_id=INVENTORY_UPSTREAM_ID,
        endpoint="http://127.0.0.1:9003",
    ),
)


def make_context() -> RequestContext:
    return RequestContext(
        request_id="request-multi-scenario",
        trace_id="5" * 32,
        protocol_version="2026-07-28",
        protocol_era=ProtocolEra.MODERN,
        tenant_id=TENANT_A_ID,
        principal_id="multi-scenario-reviewer",
        authn_method="test",
    )


async def seed_registry(session: AsyncSession) -> None:
    tenant_uuid = uuid.UUID(TENANT_A_ID)
    session.add(TenantModel(id=tenant_uuid, name="Multi Scenario Tenant", status="active"))
    await session.flush()
    for scenario in SCENARIOS:
        session.add(
            UpstreamServiceModel(
                id=uuid.UUID(scenario.upstream_id),
                tenant_id=tenant_uuid,
                namespace=scenario.namespace,
                name=scenario.name,
                description=f"{scenario.name} Fake API",
                owner="nexusmcp-demo",
                service_type="http",
                transport_type="http",
                endpoint=scenario.endpoint,
                auth_scheme="none",
                config_json={},
                status="active",
            )
        )
    await session.commit()


async def import_review_publish_scenario(
    scenario: Scenario,
    *,
    session_factory: async_sessionmaker[AsyncSession],
    context: RequestContext,
    clock: FixedClock,
    identifier_generator: UuidIdentifierGenerator,
) -> dict[str, ToolVersion]:
    import_result = await ImportOpenApi(
        SqlAlchemyOpenApiImportUnitOfWorkFactory(session_factory),
        LocalOpenApiDocumentReader(UPSTREAM_ROOT),
        OpenApiParser(),
        clock,
        identifier_generator,
    ).execute(
        ImportOpenApiCommand(
            context=context,
            upstream_service_id=scenario.upstream_id,
            source_ref=scenario.source_ref,
        )
    )
    async with session_factory() as observer_session:
        operations = await SqlAlchemyOpenApiImportRepository(observer_session).list_operations(
            TENANT_A_ID,
            import_result.import_job_id,
        )
    assert operations
    assert all(
        operation.conflict_status is OperationConflictStatus.NONE for operation in operations
    )

    review = ReviewImportedOperation(
        SqlAlchemyReviewUnitOfWorkFactory(session_factory),
        clock,
        identifier_generator,
    )
    catalog_uow_factory = SqlAlchemyCatalogUnitOfWorkFactory(session_factory)
    published_versions: dict[str, ToolVersion] = {}
    for operation in operations:
        result = await review.execute(
            ReviewImportedOperationCommand(
                context=context,
                operation_id=operation.id,
                owner="nexusmcp-demo",
            )
        )
        await SubmitToolVersionForReview(catalog_uow_factory, clock).execute(
            SubmitToolVersionForReviewCommand(
                context=context,
                tool_version_id=result.tool_version_id,
            )
        )
        async with session_factory() as observer_session:
            catalog = SqlAlchemyToolCatalogRepository(observer_session)
            bindings = SqlAlchemyToolBindingRepository(observer_session)
            version = await catalog.get_version_by_id(TENANT_A_ID, result.tool_version_id)
            binding = await bindings.get_by_id(TENANT_A_ID, result.tool_binding_id)
        assert version is not None and binding is not None
        await PublishTool(catalog_uow_factory, clock).execute(
            PublishToolCommand(
                context=context,
                tool_id=result.tool_id,
                tool_version_id=version.id,
                expected_schema_digest=version.schema_digest,
                expected_binding_digest=binding.binding_digest,
            )
        )
        published_versions[result.canonical_name] = version
    return published_versions


@pytest.mark.asyncio
async def test_three_scenarios_share_pipeline_and_catalog(
    pg_session_factory: async_sessionmaker[AsyncSession],
    migrated_database_url: str,
) -> None:
    async with pg_session_factory() as seed_session:
        await seed_registry(seed_session)
    context = make_context()
    clock = FixedClock(NOW)
    identifier_generator = UuidIdentifierGenerator()
    versions: dict[str, ToolVersion] = {}

    for scenario in SCENARIOS:
        versions.update(
            await import_review_publish_scenario(
                scenario,
                session_factory=pg_session_factory,
                context=context,
                clock=clock,
                identifier_generator=identifier_generator,
            )
        )

    assert versions["directory.search_employees"].side_effect is ToolSideEffect.READ_ONLY
    assert versions["ops.acknowledge_incident"].side_effect is ToolSideEffect.IDEMPOTENT_WRITE
    assert versions["inventory.reserve_stock"].side_effect is ToolSideEffect.NON_IDEMPOTENT_WRITE
    assert "ops.get_status" in versions
    assert "inventory.get_status" in versions

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

    assert [tool.name for tool in tools.tools] == [
        "directory.get_employee",
        "directory.list_employees",
        "directory.search_employees",
        "inventory.get_status",
        "inventory.reserve_stock",
        "ops.acknowledge_incident",
        "ops.get_status",
    ]
