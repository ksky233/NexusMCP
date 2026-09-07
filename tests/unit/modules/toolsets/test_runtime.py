"""Toolset Data Plane Scope、Grant 与 Membership Guard。"""

from datetime import UTC, datetime

import pytest

from nexusmcp.modules.catalog.adapters.in_memory import InMemoryToolCatalogRepository
from nexusmcp.modules.catalog.domain import PublishedTool, ToolSideEffect, ToolVisibility
from nexusmcp.modules.toolsets.adapters.in_memory import (
    InMemoryToolsetCatalogReader,
    InMemoryToolsetRepository,
)
from nexusmcp.modules.toolsets.adapters.in_memory_uow import InMemoryToolsetUnitOfWorkFactory
from nexusmcp.modules.toolsets.domain import Toolset, ToolsetMemberAvailability
from nexusmcp.modules.toolsets.ports import ToolsetCatalogSnapshot
from nexusmcp.modules.toolsets.runtime import (
    McpEndpointScope,
    ResolveToolsetAccess,
)
from nexusmcp.shared.errors import (
    ToolsetAccessDeniedError,
    ToolsetMemberUnavailableError,
    ToolsetNotActiveError,
    ToolsetNotFoundError,
)
from nexusmcp.shared.request_context import ProtocolEra, RequestContext

NOW = datetime(2026, 9, 7, tzinfo=UTC)


def context(principal_id: str = "operations-agent") -> RequestContext:
    return RequestContext(
        request_id="request-runtime",
        trace_id="a" * 32,
        tenant_id="tenant-a",
        principal_id=principal_id,
        authn_method="test",
        protocol_version="2026-07-28",
        protocol_era=ProtocolEra.MODERN,
    )


def published(tool_id: str, name: str) -> PublishedTool:
    return PublishedTool(
        tool_id=tool_id,
        tool_version_id=f"{tool_id}-v1",
        tenant_id="tenant-a",
        canonical_name=name,
        display_name=name,
        description=name,
        input_schema={"type": "object", "properties": {}},
        output_schema=None,
        version=1,
        visibility=ToolVisibility.PUBLIC,
        side_effect=ToolSideEffect.READ_ONLY,
        schema_digest="1" * 64,
    )


def explicit_toolset(
    *,
    toolset_id: str = "toolset-operations",
    slug: str = "operations",
    tool_ids: tuple[str, ...] = ("tool-operations",),
    principal_ids: tuple[str, ...] = ("operations-agent",),
    active: bool = True,
) -> Toolset:
    toolset = (
        Toolset.create_explicit(
            toolset_id=toolset_id,
            tenant_id="tenant-a",
            slug=slug,
            name=slug,
            description=None,
            created_by="admin-a",
            created_at=NOW,
        )
        .replace_members(
            expected_revision=1,
            tool_ids=tool_ids,
            actor_id="admin-a",
            occurred_at=NOW,
        )
        .replace_grants(
            expected_revision=2,
            principal_ids=principal_ids,
            actor_id="admin-a",
            occurred_at=NOW,
        )
    )
    return toolset.activate(expected_revision=3, activated_at=NOW) if active else toolset


def resolver(*toolsets: Toolset) -> ResolveToolsetAccess:
    snapshots = (
        ToolsetCatalogSnapshot(
            tool_id="tool-operations",
            tenant_id="tenant-a",
            availability=ToolsetMemberAvailability.AVAILABLE,
            published_tool_version_id="tool-operations-v1",
            canonical_name="operations.get_incident",
        ),
        ToolsetCatalogSnapshot(
            tool_id="tool-risk",
            tenant_id="tenant-a",
            availability=ToolsetMemberAvailability.AVAILABLE,
            published_tool_version_id="tool-risk-v1",
            canonical_name="risk.get_score",
        ),
        ToolsetCatalogSnapshot(
            tool_id="tool-disabled",
            tenant_id="tenant-a",
            availability=ToolsetMemberAvailability.TOOL_DISABLED,
            published_tool_version_id=None,
            canonical_name="operations.disabled_tool",
        ),
    )
    return ResolveToolsetAccess(
        InMemoryToolsetUnitOfWorkFactory(
            toolsets=InMemoryToolsetRepository(toolsets),
            catalog=InMemoryToolsetCatalogReader(snapshots),
        ),
        InMemoryToolCatalogRepository(
            published_tools=(
                published("tool-operations", "operations.get_incident"),
                published("tool-risk", "risk.get_score"),
            )
        ),
    )


@pytest.mark.asyncio
async def test_scoped_access_returns_only_active_granted_members_and_guards_call() -> None:
    access = await resolver(explicit_toolset()).execute(
        context(),
        McpEndpointScope.toolset("operations"),
    )

    assert [tool.canonical_name for tool in access.tools] == ["operations.get_incident"]
    assert access.toolset_id == "toolset-operations"
    access.require_business_tool("operations.get_incident")
    with pytest.raises(ToolsetAccessDeniedError):
        access.require_business_tool("risk.get_score")


@pytest.mark.asyncio
async def test_scoped_access_rejects_unknown_inactive_or_ungranted_toolset() -> None:
    active = explicit_toolset()
    resolve = resolver(active)
    with pytest.raises(ToolsetNotFoundError):
        await resolve.execute(context(), McpEndpointScope.toolset("unknown"))
    with pytest.raises(ToolsetAccessDeniedError):
        await resolve.execute(context("risk-agent"), McpEndpointScope.toolset("operations"))

    inactive = explicit_toolset(active=False)
    with pytest.raises(ToolsetNotActiveError):
        await resolver(inactive).execute(context(), McpEndpointScope.toolset("operations"))


@pytest.mark.asyncio
async def test_root_access_is_distinct_union_of_all_granted_active_toolsets() -> None:
    operations = explicit_toolset()
    cross_domain = explicit_toolset(
        toolset_id="toolset-cross-domain",
        slug="risk-operations",
        tool_ids=("tool-operations", "tool-risk"),
    )
    access = await resolver(operations, cross_domain).execute(context(), McpEndpointScope.root())

    assert [tool.canonical_name for tool in access.tools] == [
        "operations.get_incident",
        "risk.get_score",
    ]
    assert access.toolset_id is None


@pytest.mark.asyncio
async def test_all_published_is_dynamic_projection_without_member_rows() -> None:
    system = Toolset.create_all_published(
        toolset_id="toolset-all-published",
        tenant_id="tenant-a",
        created_by="system",
        created_at=NOW,
    ).replace_grants(
        expected_revision=1,
        principal_ids=("operations-agent",),
        actor_id="system",
        occurred_at=NOW,
    )

    access = await resolver(system).execute(
        context(),
        McpEndpointScope.toolset("all-published"),
    )

    assert [tool.canonical_name for tool in access.tools] == [
        "operations.get_incident",
        "risk.get_score",
    ]
    assert system.tool_ids == ()


@pytest.mark.asyncio
async def test_guard_distinguishes_unavailable_member_from_non_member() -> None:
    toolset = explicit_toolset(tool_ids=("tool-operations", "tool-disabled"))
    access = await resolver(toolset).execute(context(), McpEndpointScope.toolset("operations"))

    with pytest.raises(ToolsetMemberUnavailableError):
        access.require_business_tool("operations.disabled_tool")
    with pytest.raises(ToolsetAccessDeniedError):
        access.require_business_tool("inventory.get_sku")
