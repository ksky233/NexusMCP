"""Catalog 可见性 Use Case 单元测试。"""

import pytest

from nexusmcp.modules.catalog.adapters.in_memory import InMemoryToolCatalogRepository
from nexusmcp.modules.catalog.domain import PublishedTool, ToolSideEffect, ToolVisibility
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


def _published_tool(name: str, visibility: ToolVisibility) -> PublishedTool:
    return PublishedTool(
        tool_id=f"tool-{name}",
        tool_version_id=f"version-{name}",
        tenant_id="tenant-a",
        canonical_name=name,
        display_name=name,
        description=f"Tool {name}",
        input_schema={"type": "object", "properties": {}},
        output_schema=None,
        version=1,
        visibility=visibility,
        side_effect=ToolSideEffect.READ_ONLY,
        schema_digest=f"schema-{name}",
    )


@pytest.mark.asyncio
async def test_list_visible_tools_applies_coarse_visibility_and_sorts_names() -> None:
    repository = InMemoryToolCatalogRepository(
        published_tools=[
            _published_tool("ops.restricted", ToolVisibility.RESTRICTED),
            _published_tool("inventory.list_items", ToolVisibility.AUTHENTICATED),
            _published_tool("directory.get_employee", ToolVisibility.PUBLIC),
        ]
    )
    use_case = ListVisibleTools(repository)

    anonymous = await use_case.execute(ListVisibleToolsQuery(_context("anonymous")))
    operator = await use_case.execute(ListVisibleToolsQuery(_context("operator")))

    assert [tool.canonical_name for tool in anonymous] == ["directory.get_employee"]
    assert [tool.canonical_name for tool in operator] == [
        "directory.get_employee",
        "inventory.list_items",
    ]
