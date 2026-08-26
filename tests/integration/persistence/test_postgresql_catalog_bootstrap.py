"""Application Lifespan 到 MCP tools/list 的真实 PostgreSQL 纵向集成测试。"""

import uuid
from datetime import UTC, datetime

import httpx2
import pytest
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from nexusmcp.bootstrap.app import create_app
from nexusmcp.bootstrap.config import Settings
from nexusmcp.infrastructure.persistence.runtime import DatabaseRuntime
from nexusmcp.modules.catalog.adapters.sqlalchemy_models import ToolModel, ToolVersionModel
from nexusmcp.modules.connectors.adapters.sqlalchemy_models import ToolBindingModel
from nexusmcp.modules.identity.adapters.sqlalchemy_models import TenantModel
from nexusmcp.modules.registry.adapters.sqlalchemy_models import UpstreamServiceModel
from tests.contract.repositories.contracts import (
    BINDING_ID,
    TENANT_A_ID,
    TOOL_ID,
    UPSTREAM_ID,
    VERSION_ID,
)

pytestmark = pytest.mark.integration


async def seed_published_tool(session: AsyncSession) -> None:
    tenant_uuid = uuid.UUID(TENANT_A_ID)
    tool_uuid = uuid.UUID(TOOL_ID)
    version_uuid = uuid.UUID(VERSION_ID)
    upstream_uuid = uuid.UUID(UPSTREAM_ID)
    published_at = datetime(2026, 8, 25, 12, 0, tzinfo=UTC)

    session.add(TenantModel(id=tenant_uuid, name="Bootstrap Tenant", status="active"))
    await session.flush()
    session.add(
        UpstreamServiceModel(
            id=upstream_uuid,
            tenant_id=tenant_uuid,
            namespace="directory",
            name="employee-directory",
            description="Bootstrap integration upstream",
            owner="people-platform",
            service_type="http",
            transport_type="http",
            endpoint="http://127.0.0.1:9001",
            auth_scheme="none",
            config_json={},
            status="active",
        )
    )
    session.add(
        ToolModel(
            id=tool_uuid,
            tenant_id=tenant_uuid,
            namespace="directory",
            canonical_name="directory.get_employee",
            owner="people-platform",
            status="active",
        )
    )
    await session.flush()
    session.add(
        ToolVersionModel(
            id=version_uuid,
            tenant_id=tenant_uuid,
            tool_id=tool_uuid,
            version=1,
            display_name="Get employee",
            description="Get one employee by id.",
            input_schema_json={
                "type": "object",
                "properties": {"employee_id": {"type": "string"}},
                "required": ["employee_id"],
            },
            output_schema_json=None,
            schema_digest="1" * 64,
            tags_json=["directory"],
            side_effect="read_only",
            visibility="public",
            status="published",
            created_by="bootstrap-test",
            created_at=published_at,
            reviewed_at=published_at,
            published_at=published_at,
        )
    )
    await session.flush()
    session.add(
        ToolBindingModel(
            id=uuid.UUID(BINDING_ID),
            tenant_id=tenant_uuid,
            tool_version_id=version_uuid,
            upstream_service_id=upstream_uuid,
            imported_operation_id=None,
            binding_type="http",
            binding_config_json={
                "method": "GET",
                "path_template": "/employees/{employee_id}",
            },
            binding_digest="2" * 64,
            status="published",
            published_at=published_at,
        )
    )
    await session.commit()


@pytest.mark.asyncio
async def test_postgresql_lifespan_readiness_and_mcp_catalog_query(
    pg_session_factory: async_sessionmaker[AsyncSession],
    migrated_database_url: str,
) -> None:
    async with pg_session_factory() as seed_session:
        await seed_published_tool(seed_session)
    app = create_app(
        Settings(
            environment="test",
            catalog_backend="postgresql",
            database_url=SecretStr(migrated_database_url),
            local_tenant_id=TENANT_A_ID,
        )
    )
    runtime = app.state.database_runtime
    assert isinstance(runtime, DatabaseRuntime)
    assert runtime.is_started is False

    transport = httpx2.ASGITransport(app=app)
    async with httpx2.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as http_client:
        before_start = await http_client.get("/health/ready")
        assert before_start.status_code == 503

        async with app.router.lifespan_context(app):
            readiness = await http_client.get("/health/ready")
            assert readiness.status_code == 200
            mcp_transport = streamable_http_client(
                "http://testserver/mcp",
                http_client=http_client,
            )
            async with Client(mcp_transport) as client:
                result = await client.list_tools(cache_mode="refresh")

        after_stop = await http_client.get("/health/ready")

    assert [tool.name for tool in result.tools] == [
        "nexus.search_tools",
        "directory.get_employee",
    ]
    assert result.tools[1].input_schema["required"] == ["employee_id"]
    assert runtime.is_started is False
    assert after_stop.status_code == 503
