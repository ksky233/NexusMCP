"""Scope Denial Audit 故障不遮蔽原始 MCP 拒绝。"""

import logging
from datetime import UTC, datetime

import httpx2
import pytest
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from mcp.server.transport_security import TransportSecuritySettings

from nexusmcp.interfaces.mcp.http_transport import create_mcp_http_transport
from nexusmcp.interfaces.mcp.server import create_mcp_server
from nexusmcp.modules.catalog.adapters.in_memory import InMemoryToolCatalogRepository
from nexusmcp.modules.catalog.domain import PublishedTool, ToolSideEffect, ToolVisibility
from nexusmcp.modules.catalog.search import SearchPublishedTools
from nexusmcp.modules.catalog.use_cases import ListVisibleTools
from nexusmcp.modules.execution.lifecycle import RecordMcpScopeDenialCommand
from nexusmcp.modules.identity.adapters.context_principal import ContextPrincipalResolver
from nexusmcp.modules.policy.adapters.static_read_only import StaticReadOnlyPolicyEvaluator
from nexusmcp.modules.tool_search.search_tools import SearchTools
from nexusmcp.modules.toolsets.adapters.in_memory import (
    InMemoryToolsetCatalogReader,
    InMemoryToolsetRepository,
)
from nexusmcp.modules.toolsets.adapters.in_memory_uow import InMemoryToolsetUnitOfWorkFactory
from nexusmcp.modules.toolsets.domain import Toolset, ToolsetMemberAvailability
from nexusmcp.modules.toolsets.ports import ToolsetCatalogSnapshot
from nexusmcp.modules.toolsets.runtime import ResolveToolsetAccess

NOW = datetime(2026, 9, 7, tzinfo=UTC)


class FailingScopeDenialAudit:
    def __init__(self) -> None:
        self.calls: list[RecordMcpScopeDenialCommand] = []

    async def record_scope_denial(self, command: RecordMcpScopeDenialCommand) -> None:
        self.calls.append(command)
        raise RuntimeError("audit store unavailable")


@pytest.mark.asyncio
async def test_audit_failure_preserves_original_scope_denial_response(
    caplog: pytest.LogCaptureFixture,
) -> None:
    published = PublishedTool(
        tool_id="tool-1",
        tool_version_id="tool-1-v1",
        tenant_id="local",
        canonical_name="directory.get_employee",
        display_name="Get employee",
        description="Get one employee.",
        input_schema={"type": "object", "properties": {}},
        output_schema=None,
        version=1,
        visibility=ToolVisibility.PUBLIC,
        side_effect=ToolSideEffect.READ_ONLY,
        schema_digest="1" * 64,
    )
    catalog = InMemoryToolCatalogRepository(published_tools=(published,))
    toolset = (
        Toolset.create_explicit(
            toolset_id="toolset-1",
            tenant_id="local",
            slug="directory",
            name="Directory",
            description=None,
            created_by="admin",
            created_at=NOW,
        )
        .replace_members(
            expected_revision=1,
            tool_ids=(published.tool_id,),
            actor_id="admin",
            occurred_at=NOW,
        )
        .replace_grants(
            expected_revision=2,
            principal_ids=("anonymous",),
            actor_id="admin",
            occurred_at=NOW,
        )
        .activate(expected_revision=3, activated_at=NOW)
    )
    resolver = ResolveToolsetAccess(
        InMemoryToolsetUnitOfWorkFactory(
            toolsets=InMemoryToolsetRepository((toolset,)),
            catalog=InMemoryToolsetCatalogReader(
                (
                    ToolsetCatalogSnapshot(
                        tool_id=published.tool_id,
                        tenant_id="local",
                        availability=ToolsetMemberAvailability.AVAILABLE,
                        published_tool_version_id=published.tool_version_id,
                        canonical_name=published.canonical_name,
                    ),
                )
            ),
        ),
        catalog,
    )
    search = SearchTools(
        lexical_search=SearchPublishedTools(catalog),
        principal_resolver=ContextPrincipalResolver(),
        policy_evaluator=StaticReadOnlyPolicyEvaluator(),
    )
    audit = FailingScopeDenialAudit()
    server = create_mcp_server(
        ListVisibleTools(catalog),
        search_tools=search,
        resolve_toolset_access=resolver,
        scope_audit=audit,
    )
    transport = create_mcp_http_transport(
        server,
        transport_security=TransportSecuritySettings(
            allowed_hosts=["testserver", "testserver:*"],
            allowed_origins=[],
        ),
    )
    caplog.set_level(logging.ERROR, logger="nexusmcp.interfaces.mcp.server")

    async with transport.session_manager.run():
        async with httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=transport.app),
            base_url="http://testserver",
        ) as http_client:
            mcp_transport = streamable_http_client(
                "http://testserver/mcp/toolsets/directory",
                http_client=http_client,
            )
            async with Client(mcp_transport) as client:
                result = await client.call_tool(
                    "nexus.search_tools",
                    {"query": "employee", "retrieval_mode": "lexical"},
                )

    assert result.is_error is True
    assert result.meta is not None
    assert result.meta["com.nexusmcp/errorCode"] == "toolset_access_denied"
    assert len(audit.calls) == 1
    record = next(
        record for record in caplog.records if record.msg == "mcp_scope_denial_audit_failed"
    )
    assert record.__dict__["error_code"] == "audit_write_failed"
    assert record.__dict__["original_error_code"] == "toolset_access_denied"
