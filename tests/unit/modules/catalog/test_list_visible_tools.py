"""Catalog 可见性与生命周期不变量单元测试。"""

import pytest

from nexusmcp.modules.catalog.adapters.in_memory import InMemoryToolRepository
from nexusmcp.modules.catalog.domain import ToolDefinition, ToolStatus, ToolVisibility
from nexusmcp.modules.catalog.use_cases import ListVisibleTools, ListVisibleToolsQuery
from nexusmcp.shared.request_context import ProtocolEra, RequestContext


def _context(principal_id: str) -> RequestContext:
    return RequestContext(
        request_id="req-001",
        trace_id="0" * 32,
        protocol_version="2026-07-28",
        protocol_era=ProtocolEra.MODERN,
        tenant_id="tenant-a",
        principal_id=principal_id,
        authn_method="test",
    )


def _tool(
    tool_id: str,
    name: str,
    *,
    status: ToolStatus = ToolStatus.PUBLISHED,
    visibility: ToolVisibility = ToolVisibility.PUBLIC,
    allowed: frozenset[str] = frozenset(),
) -> ToolDefinition:
    return ToolDefinition(
        id=tool_id,
        tenant_id="tenant-a",
        canonical_name=name,
        display_name=name,
        description=f"Tool {name}",
        input_schema={"type": "object", "properties": {}},
        status=status,
        visibility=visibility,
        allowed_principal_ids=allowed,
    )


@pytest.mark.asyncio
async def test_list_visible_tools_filters_lifecycle_and_principal() -> None:
    repository = InMemoryToolRepository(
        [
            _tool("tool-public", "directory.public"),
            _tool(
                "tool-restricted",
                "ops.restricted",
                visibility=ToolVisibility.RESTRICTED,
                allowed=frozenset({"operator"}),
            ),
            _tool("tool-draft", "inventory.draft", status=ToolStatus.DRAFT),
        ]
    )
    use_case = ListVisibleTools(repository)

    anonymous = await use_case.execute(ListVisibleToolsQuery(_context("anonymous")))
    operator = await use_case.execute(ListVisibleToolsQuery(_context("operator")))

    assert [tool.canonical_name for tool in anonymous] == ["directory.public"]
    assert [tool.canonical_name for tool in operator] == [
        "directory.public",
        "ops.restricted",
    ]


def test_restricted_tool_requires_allowed_principals() -> None:
    with pytest.raises(ValueError, match="restricted tool"):
        _tool(
            "invalid",
            "invalid.restricted",
            visibility=ToolVisibility.RESTRICTED,
        )
