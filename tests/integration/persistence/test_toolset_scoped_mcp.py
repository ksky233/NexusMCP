"""I03-3 Toolset Scoped MCP 的真实协议、授权与执行回归。"""

import uuid

import httpx
import httpx2
import pytest
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from mcp.shared.exceptions import MCPError
from pydantic import SecretStr
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from nexusmcp.bootstrap.app import create_app
from nexusmcp.bootstrap.config import Settings
from nexusmcp.modules.audit.domain import AuditOutcome
from nexusmcp.modules.catalog.adapters.sqlalchemy_models import ToolModel
from nexusmcp.modules.execution.domain import McpScopeType
from nexusmcp.modules.toolsets.adapters.sqlalchemy_repository import (
    SqlAlchemyToolsetRepository,
)
from nexusmcp.modules.toolsets.domain import ToolsetDiscoveryMode
from tests.contract.repositories.contracts import TENANT_A_ID, TOOL_ID
from tests.contract.repositories.toolset_contracts import NOW as TOOLSET_NOW
from tests.contract.repositories.toolset_contracts import make_toolset
from tests.integration.persistence.test_mcp_read_only_http_call import seed_executable_tool

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_modern_scoped_endpoint_lists_calls_and_guards_without_root_bypass(
    pg_session_factory: async_sessionmaker[AsyncSession],
    migrated_database_url: str,
) -> None:
    async with pg_session_factory() as seed_session:
        await seed_executable_tool(
            seed_session,
            upstream_endpoint="http://127.0.0.1:9001",
        )
        toolset = make_toolset(active=True, principal_ids=("operations-agent",))
        search_toolset = make_toolset(
            toolset_id="00000000-0000-0000-0000-000000000520",
            slug="search-operations",
            active=True,
            principal_ids=("operations-agent",),
        ).update_profile(
            expected_revision=4,
            name="Search Operations",
            description="Search-first operations tools",
            discovery_mode=ToolsetDiscoveryMode.SEARCH_FIRST,
            updated_at=TOOLSET_NOW,
        )
        await SqlAlchemyToolsetRepository(seed_session).add(TENANT_A_ID, toolset)
        await SqlAlchemyToolsetRepository(seed_session).add(TENANT_A_ID, search_toolset)
        await seed_session.commit()

    upstream_calls: list[httpx.Request] = []

    def upstream_handler(request: httpx.Request) -> httpx.Response:
        upstream_calls.append(request)
        return httpx.Response(
            200,
            json={
                "employee_id": "emp-001",
                "name": "Ada Chen",
                "department": "engineering",
                "status": "active",
                "email": "ada.chen@example.test",
            },
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(upstream_handler)
    ) as upstream_client:
        app = create_app(
            Settings(
                environment="test",
                catalog_backend="postgresql",
                database_url=SecretStr(migrated_database_url),
                local_tenant_id=TENANT_A_ID,
                static_agent_principal_id="operations-agent",
                tool_execution_enabled=True,
                upstream_egress_policy_enabled=True,
                upstream_allowed_ports=[9001],
                upstream_allow_local_demo=True,
            ),
            tool_http_client=upstream_client,
        )
        async with app.router.lifespan_context(app):
            async with httpx2.AsyncClient(
                transport=httpx2.ASGITransport(app=app),
                base_url="http://testserver",
            ) as http_client:
                scoped_transport = streamable_http_client(
                    "http://testserver/mcp/toolsets/operations",
                    http_client=http_client,
                )
                async with Client(scoped_transport) as scoped_client:
                    scoped_list = await scoped_client.list_tools(cache_mode="refresh")
                    meta_bypass = await scoped_client.call_tool(
                        "nexus.search_tools",
                        {"query": "employee", "retrieval_mode": "lexical"},
                    )
                    member_bypass = await scoped_client.call_tool("inventory.get_sku", {})
                    success = await scoped_client.call_tool(
                        "directory.get_employee",
                        {"employee_id": "emp-001"},
                    )

                search_transport = streamable_http_client(
                    "http://testserver/mcp/toolsets/search-operations",
                    http_client=http_client,
                )
                async with Client(search_transport) as search_client:
                    search_list = await search_client.list_tools(cache_mode="refresh")
                    searched = await search_client.call_tool(
                        "nexus.search_tools",
                        {"query": "employee", "retrieval_mode": "lexical"},
                    )

                unknown_transport = streamable_http_client(
                    "http://testserver/mcp/toolsets/unknown",
                    http_client=http_client,
                )
                unknown_error: MCPError | None = None
                async with Client(unknown_transport) as unknown_client:
                    try:
                        await unknown_client.list_tools(cache_mode="refresh")
                    except MCPError as error:
                        unknown_error = error

                root_transport = streamable_http_client(
                    "http://testserver/mcp",
                    http_client=http_client,
                )
                async with Client(root_transport) as root_client:
                    root_list = await root_client.list_tools(cache_mode="refresh")
                    root_bypass = await root_client.call_tool("inventory.get_sku", {})

                async with pg_session_factory() as state_session:
                    await state_session.execute(
                        update(ToolModel)
                        .where(ToolModel.id == uuid.UUID(TOOL_ID))
                        .values(status="disabled")
                    )
                    await state_session.commit()
                degraded_transport = streamable_http_client(
                    "http://testserver/mcp/toolsets/operations",
                    http_client=http_client,
                )
                async with Client(degraded_transport) as degraded_client:
                    unavailable = await degraded_client.call_tool(
                        "directory.get_employee",
                        {"employee_id": "emp-001"},
                    )

                legacy = await http_client.post(
                    "/mcp/toolsets/operations",
                    headers={
                        "accept": "application/json, text/event-stream",
                        "content-type": "application/json",
                        "mcp-protocol-version": "2025-11-25",
                    },
                    json={
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "initialize",
                        "params": {
                            "protocolVersion": "2025-11-25",
                            "capabilities": {},
                            "clientInfo": {"name": "legacy-probe", "version": "0.1.0"},
                        },
                    },
                )

            executions = await app.state.execution_reader.list_by_tenant(TENANT_A_ID)
            audits = await app.state.audit_reader.list_by_tenant(TENANT_A_ID)

    assert [tool.name for tool in scoped_list.tools] == ["directory.get_employee"]
    assert meta_bypass.is_error is True
    assert meta_bypass.meta is not None
    assert meta_bypass.meta["com.nexusmcp/errorCode"] == "toolset_access_denied"
    assert member_bypass.is_error is True
    assert member_bypass.meta is not None
    assert member_bypass.meta["com.nexusmcp/errorCode"] == "toolset_access_denied"
    assert success.is_error is False
    assert success.structured_content["name"] == "Ada Chen"
    assert [tool.name for tool in search_list.tools] == ["nexus.search_tools"]
    assert searched.structured_content["tools"][0]["name"] == "directory.get_employee"
    assert unknown_error is not None
    assert unknown_error.data == {"errorCode": "toolset_not_found"}
    assert [tool.name for tool in root_list.tools] == [
        "nexus.search_tools",
        "directory.get_employee",
    ]
    assert root_bypass.is_error is True
    assert root_bypass.meta is not None
    assert root_bypass.meta["com.nexusmcp/errorCode"] == "toolset_access_denied"
    assert unavailable.is_error is True
    assert unavailable.meta is not None
    assert unavailable.meta["com.nexusmcp/errorCode"] == "toolset_member_unavailable"
    assert legacy.status_code == 400
    assert legacy.json()["error"]["data"] == {
        "errorCode": "unsupported_protocol",
        "requested": "2025-11-25",
    }
    assert len(executions) == 1
    assert executions[0].mcp_scope_type is McpScopeType.TOOLSET
    assert executions[0].toolset_id == toolset.id
    assert executions[0].toolset_revision == toolset.revision
    assert executions[0].policy_reason_code == "read_only_allowed"
    assert len(upstream_calls) == 1
    execution_audits = [event for event in audits if event.execution_id == executions[0].id]
    assert [event.outcome for event in execution_audits] == [
        AuditOutcome.ALLOWED,
        AuditOutcome.SUCCEEDED,
    ]
    assert all(
        event.metadata is not None
        and event.metadata["mcp_scope_type"] == "toolset"
        and event.metadata["scope_reason_code"] == "active_toolset_grant"
        and event.metadata["toolset_id"] == toolset.id
        and event.metadata["toolset_revision"] == toolset.revision
        for event in execution_audits
    )
    denial_audits = [event for event in audits if event.outcome is AuditOutcome.DENIED]
    assert [event.reason_code for event in denial_audits] == [
        "toolset_access_denied",
        "toolset_access_denied",
        "toolset_access_denied",
        "toolset_member_unavailable",
    ]
    assert all("arguments" not in (event.metadata or {}) for event in denial_audits)
