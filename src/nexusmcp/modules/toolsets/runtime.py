"""MCP Data Plane 的 Toolset Scope 解析与调用防绕过。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from nexusmcp.modules.catalog.domain import PublishedTool
from nexusmcp.modules.catalog.ports import PublishedToolReader
from nexusmcp.modules.toolsets.domain import (
    Toolset,
    ToolsetDiscoveryMode,
    ToolsetKind,
    ToolsetMemberAvailability,
    ToolsetStatus,
)
from nexusmcp.modules.toolsets.ports import (
    ToolsetCatalogReader,
    ToolsetCatalogSnapshot,
    ToolsetUnitOfWorkFactory,
)
from nexusmcp.shared.errors import (
    ToolsetAccessDeniedError,
    ToolsetMemberUnavailableError,
    ToolsetNotActiveError,
    ToolsetNotFoundError,
)
from nexusmcp.shared.request_context import RequestContext


class McpEndpointScopeType(StrEnum):
    ROOT = "root"
    TOOLSET = "toolset"


@dataclass(frozen=True, slots=True)
class McpEndpointScope:
    type: McpEndpointScopeType
    toolset_slug: str | None = None

    def __post_init__(self) -> None:
        if self.type is McpEndpointScopeType.ROOT and self.toolset_slug is not None:
            raise ValueError("root endpoint scope must not contain toolset slug")
        if self.type is McpEndpointScopeType.TOOLSET and not self.toolset_slug:
            raise ValueError("toolset endpoint scope requires slug")

    @classmethod
    def root(cls) -> McpEndpointScope:
        return cls(type=McpEndpointScopeType.ROOT)

    @classmethod
    def toolset(cls, slug: str) -> McpEndpointScope:
        return cls(type=McpEndpointScopeType.TOOLSET, toolset_slug=slug)


@dataclass(frozen=True, slots=True)
class ResolvedToolsetAccess:
    endpoint_scope: McpEndpointScope
    tools: tuple[PublishedTool, ...]
    unavailable_tool_names: frozenset[str]
    discovery_mode: ToolsetDiscoveryMode | None
    toolset_id: str | None = None
    toolset_revision: int | None = None

    @property
    def available_tool_ids(self) -> frozenset[str]:
        return frozenset(tool.tool_id for tool in self.tools)

    def require_business_tool(self, canonical_name: str) -> None:
        if any(tool.canonical_name == canonical_name for tool in self.tools):
            return
        if canonical_name in self.unavailable_tool_names:
            raise ToolsetMemberUnavailableError(
                f"tool {canonical_name} was a member but is currently unavailable"
            )
        raise ToolsetAccessDeniedError(
            f"tool {canonical_name} was outside the authorized endpoint scope"
        )


class ResolveToolsetAccess:
    def __init__(
        self,
        unit_of_work_factory: ToolsetUnitOfWorkFactory,
        published_tools: PublishedToolReader,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._published_tools = published_tools

    async def execute(
        self,
        context: RequestContext,
        endpoint_scope: McpEndpointScope,
    ) -> ResolvedToolsetAccess:
        async with self._unit_of_work_factory() as unit_of_work:
            if endpoint_scope.type is McpEndpointScopeType.TOOLSET:
                assert endpoint_scope.toolset_slug is not None
                toolset = await unit_of_work.toolsets.get_by_slug(
                    context.tenant_id,
                    endpoint_scope.toolset_slug,
                )
                _require_scoped_access(toolset, context)
                assert toolset is not None
                toolsets = (toolset,)
            else:
                toolsets = await unit_of_work.toolsets.list_granted_active(
                    context.tenant_id,
                    context.principal_id,
                )
            allowed_all_published = any(
                toolset.kind is ToolsetKind.ALL_PUBLISHED for toolset in toolsets
            )
            snapshots = await _member_snapshots(
                unit_of_work.catalog,
                context.tenant_id,
                toolsets,
            )

        published = await self._published_tools.list_published_by_tenant(context.tenant_id)
        allowed_ids = frozenset(snapshot.tool_id for snapshot in snapshots)
        eligible = tuple(
            sorted(
                (
                    tool
                    for tool in published
                    if (allowed_all_published or tool.tool_id in allowed_ids)
                    and tool.is_visible_to(context.principal_id)
                ),
                key=lambda tool: tool.canonical_name,
            )
        )
        published_ids = {tool.tool_id for tool in published}
        unavailable_names = frozenset(
            snapshot.canonical_name
            for snapshot in snapshots
            if snapshot.canonical_name is not None
            and (
                snapshot.availability is not ToolsetMemberAvailability.AVAILABLE
                or snapshot.tool_id not in published_ids
            )
        )
        scoped_toolset = (
            toolsets[0] if endpoint_scope.type is McpEndpointScopeType.TOOLSET else None
        )
        return ResolvedToolsetAccess(
            endpoint_scope=endpoint_scope,
            tools=eligible,
            unavailable_tool_names=unavailable_names,
            discovery_mode=(scoped_toolset.discovery_mode if scoped_toolset is not None else None),
            toolset_id=scoped_toolset.id if scoped_toolset is not None else None,
            toolset_revision=scoped_toolset.revision if scoped_toolset is not None else None,
        )


def _require_scoped_access(toolset: Toolset | None, context: RequestContext) -> None:
    if toolset is None:
        raise ToolsetNotFoundError("toolset slug did not exist in tenant")
    if toolset.status is not ToolsetStatus.ACTIVE:
        raise ToolsetNotActiveError("toolset endpoint was not active")
    if context.principal_id not in toolset.principal_ids:
        raise ToolsetAccessDeniedError("principal did not have an active toolset grant")


async def _member_snapshots(
    catalog: ToolsetCatalogReader,
    tenant_id: str,
    toolsets: tuple[Toolset, ...],
) -> tuple[ToolsetCatalogSnapshot, ...]:
    tool_ids = tuple(
        sorted(
            {
                tool_id
                for toolset in toolsets
                if toolset.kind is ToolsetKind.EXPLICIT
                for tool_id in toolset.tool_ids
            }
        )
    )
    return await catalog.list_member_snapshots(tenant_id, tool_ids)
