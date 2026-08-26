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
from tests.contract.repositories.contracts import (
    BINDING_ID,
    TENANT_A_ID,
    TOOL_ID,
    UPSTREAM_ID,
    VERSION_ID,
)

pytestmark = pytest.mark.integration


async def seed_executable_tool(
    session: AsyncSession,
    *,
    auth_scheme: str | None = "none",
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
            endpoint="http://employee.test",
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


@pytest.mark.asyncio
async def test_modern_mcp_read_only_http_tool_call(
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
    assert missing.meta["com.nexusmcp/errorCode"] == "tool_not_found"
    assert len(executions) == 1
    assert executions[0].status is ExecutionStatus.SUCCEEDED
    assert executions[0].request_id
    assert executions[0].trace_id
    assert [event.outcome for event in audits] == [
        AuditOutcome.ALLOWED,
        AuditOutcome.SUCCEEDED,
    ]
