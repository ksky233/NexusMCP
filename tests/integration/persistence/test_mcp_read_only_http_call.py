"""Modern MCP tools/call → PostgreSQL Resolve → HTTP Fake Upstream E2E。"""

import uuid
from datetime import UTC, datetime

import httpx
import httpx2
import pytest
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from examples.upstream_apis.employee_directory.app import app as employee_directory_app
from nexusmcp.bootstrap.app import create_app
from nexusmcp.bootstrap.config import Settings
from nexusmcp.modules.audit.domain import AuditOutcome
from nexusmcp.modules.catalog.adapters.sqlalchemy_models import ToolModel, ToolVersionModel
from nexusmcp.modules.connectors.adapters.sqlalchemy_models import ToolBindingModel
from nexusmcp.modules.execution.domain import ExecutionStatus
from nexusmcp.modules.identity.adapters.sqlalchemy_models import TenantModel
from nexusmcp.modules.registry.adapters.sqlalchemy_models import UpstreamServiceModel
from nexusmcp.modules.toolsets.adapters.sqlalchemy_repository import (
    SqlAlchemyToolsetRepository,
)
from nexusmcp.modules.toolsets.domain import Toolset
from tests.contract.repositories.contracts import (
    BINDING_ID,
    TENANT_A_ID,
    TOOL_ID,
    UPSTREAM_ID,
    VERSION_ID,
)

pytestmark = pytest.mark.integration

SYSTEM_TOOLSET_ID = "00000000-0000-0000-0000-000000000550"


async def seed_executable_tool(
    session: AsyncSession,
    *,
    auth_scheme: str | None = "none",
    upstream_endpoint: str = "http://employee.test",
) -> None:
    tenant_id = uuid.UUID(TENANT_A_ID)
    tool_id = uuid.UUID(TOOL_ID)
    version_id = uuid.UUID(VERSION_ID)
    upstream_id = uuid.UUID(UPSTREAM_ID)
    now = datetime(2026, 8, 26, 16, 0, tzinfo=UTC)
    session.add(TenantModel(id=tenant_id, name="Call Tool Tenant", status="active"))
    await session.flush()
    session.add(
        UpstreamServiceModel(
            id=upstream_id,
            tenant_id=tenant_id,
            namespace="directory",
            name="employee-directory-call",
            description="Read-only tools/call upstream",
            owner="execution-test",
            service_type="http",
            transport_type="http",
            endpoint=upstream_endpoint,
            auth_scheme=auth_scheme,
            config_json={},
            status="active",
        )
    )
    session.add(
        ToolModel(
            id=tool_id,
            tenant_id=tenant_id,
            namespace="directory",
            canonical_name="directory.get_employee",
            owner="execution-test",
            status="active",
        )
    )
    await session.flush()
    session.add(
        ToolVersionModel(
            id=version_id,
            tenant_id=tenant_id,
            tool_id=tool_id,
            version=1,
            display_name="Get employee",
            description="Get one employee by id.",
            input_schema_json={
                "type": "object",
                "properties": {"employee_id": {"type": "string", "minLength": 1}},
                "required": ["employee_id"],
                "additionalProperties": False,
            },
            output_schema_json=None,
            schema_digest="1" * 64,
            tags_json=["directory", "read"],
            search_name="directory directory.get_employee Get employee",
            search_tags="directory read",
            search_description="Get one employee by id.",
            side_effect="read_only",
            visibility="public",
            status="published",
            created_by="execution-test",
            created_at=now,
            reviewed_at=now,
            published_at=now,
        )
    )
    await session.flush()
    session.add(
        ToolBindingModel(
            id=uuid.UUID(BINDING_ID),
            tenant_id=tenant_id,
            tool_version_id=version_id,
            upstream_service_id=upstream_id,
            imported_operation_id=None,
            binding_type="http",
            binding_config_json={
                "method": "GET",
                "path_template": "/employees/{employee_id}",
                "parameters": [
                    {
                        "argument_name": "employee_id",
                        "upstream_name": "employee_id",
                        "location": "path",
                        "required": True,
                    }
                ],
                "request_body": None,
            },
            binding_digest="2" * 64,
            status="published",
            published_at=now,
        )
    )
    await session.commit()


async def seed_all_published_grants(
    session: AsyncSession,
    *principal_ids: str,
) -> None:
    now = datetime(2026, 8, 26, 16, 0, tzinfo=UTC)
    toolset = Toolset.create_all_published(
        toolset_id=SYSTEM_TOOLSET_ID,
        tenant_id=TENANT_A_ID,
        created_by="system",
        created_at=now,
    ).replace_grants(
        expected_revision=1,
        principal_ids=principal_ids,
        actor_id="system",
        occurred_at=now,
    )
    await SqlAlchemyToolsetRepository(session).add(TENANT_A_ID, toolset)
    await session.commit()


@pytest.mark.asyncio
async def test_modern_mcp_read_only_http_tool_call(
    pg_session_factory: async_sessionmaker[AsyncSession],
    migrated_database_url: str,
) -> None:
    async with pg_session_factory() as seed_session:
        await seed_executable_tool(
            seed_session,
            upstream_endpoint="http://127.0.0.1:9001",
        )
    upstream_transport = httpx.ASGITransport(app=employee_directory_app)
    async with httpx.AsyncClient(transport=upstream_transport) as upstream_client:
        app = create_app(
            Settings(
                environment="test",
                catalog_backend="postgresql",
                database_url=SecretStr(migrated_database_url),
                local_tenant_id=TENANT_A_ID,
                static_agent_principal_id="employee-directory-agent-service",
                tool_execution_enabled=True,
                upstream_egress_policy_enabled=True,
                upstream_allowed_ports=[9001],
                upstream_allow_local_demo=True,
            ),
            tool_http_client=upstream_client,
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
                    protocol_version = client.protocol_version
                    success = await client.call_tool(
                        "directory.get_employee",
                        {"employee_id": "emp-001"},
                    )
                    invalid = await client.call_tool("directory.get_employee", {})
                    missing = await client.call_tool("directory.missing", {})

            execution_reader = app.state.execution_reader
            audit_reader = app.state.audit_reader
            executions = await execution_reader.list_by_tenant(TENANT_A_ID)
            audits = await audit_reader.list_by_tenant(TENANT_A_ID)

    assert protocol_version == "2026-07-28"
    assert success.is_error is False
    assert success.structured_content["employee_id"] == "emp-001"
    assert success.structured_content["name"] == "Ada Chen"
    assert success.meta is not None
    assert success.meta["com.nexusmcp/upstreamStatus"] == 200
    assert invalid.is_error is True
    assert invalid.meta is not None
    assert invalid.meta["com.nexusmcp/errorCode"] == "invalid_arguments"
    assert missing.is_error is True
    assert missing.meta is not None
    assert missing.meta["com.nexusmcp/errorCode"] == "toolset_access_denied"
    assert len(executions) == 1
    assert executions[0].status is ExecutionStatus.SUCCEEDED
    assert executions[0].principal_id == "employee-directory-agent-service"
    assert executions[0].request_id
    assert executions[0].trace_id
    assert [event.outcome for event in audits] == [
        AuditOutcome.ALLOWED,
        AuditOutcome.SUCCEEDED,
    ]


@pytest.mark.asyncio
async def test_mcp_call_hard_denies_metadata_endpoint_before_http_and_execution(
    pg_session_factory: async_sessionmaker[AsyncSession],
    migrated_database_url: str,
) -> None:
    async with pg_session_factory() as seed_session:
        await seed_executable_tool(
            seed_session,
            upstream_endpoint="http://169.254.169.254/latest/meta-data",
        )

    def unexpected_request(_request: httpx.Request) -> httpx.Response:
        raise AssertionError("metadata endpoint must not reach HTTP transport")

    async with httpx.AsyncClient(transport=httpx.MockTransport(unexpected_request)) as client:
        app = create_app(
            Settings(
                environment="test",
                catalog_backend="postgresql",
                database_url=SecretStr(migrated_database_url),
                local_tenant_id=TENANT_A_ID,
                tool_execution_enabled=True,
                upstream_egress_policy_enabled=True,
                upstream_allowed_cidrs=["169.254.0.0/16"],
                upstream_allowed_ports=[80],
            ),
            tool_http_client=client,
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
                async with Client(mcp_transport) as mcp_client:
                    result = await mcp_client.call_tool(
                        "directory.get_employee",
                        {"employee_id": "emp-001"},
                    )
            executions = await app.state.execution_reader.list_by_tenant(TENANT_A_ID)
            audits = await app.state.audit_reader.list_by_tenant(TENANT_A_ID)

    assert result.is_error is True
    assert result.meta is not None
    assert result.meta["com.nexusmcp/errorCode"] == "unsafe_upstream_endpoint"
    assert executions == ()
    assert audits == ()


@pytest.mark.asyncio
async def test_search_first_discovers_schema_then_calls_unlisted_business_tool(
    pg_session_factory: async_sessionmaker[AsyncSession],
    migrated_database_url: str,
) -> None:
    async with pg_session_factory() as seed_session:
        await seed_executable_tool(seed_session)
    upstream_transport = httpx.ASGITransport(app=employee_directory_app)
    async with httpx.AsyncClient(transport=upstream_transport) as upstream_client:
        app = create_app(
            Settings(
                environment="test",
                catalog_backend="postgresql",
                database_url=SecretStr(migrated_database_url),
                local_tenant_id=TENANT_A_ID,
                tool_execution_enabled=True,
                tool_discovery_mode="search_first",
            ),
            tool_http_client=upstream_client,
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
                    listed = await client.list_tools(cache_mode="refresh")
                    searched = await client.call_tool(
                        "nexus.search_tools",
                        {
                            "query": "employee",
                            "retrieval_mode": "lexical",
                        },
                    )
                    candidate = searched.structured_content["tools"][0]
                    called = await client.call_tool(
                        candidate["name"],
                        {"employee_id": "emp-001"},
                    )

    assert [tool.name for tool in listed.tools] == ["nexus.search_tools"]
    assert candidate["name"] == "directory.get_employee"
    assert candidate["inputSchema"]["required"] == ["employee_id"]
    assert called.is_error is False
    assert called.structured_content["name"] == "Ada Chen"
