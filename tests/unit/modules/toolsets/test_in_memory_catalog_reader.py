"""Toolset 同事务 Catalog Snapshot InMemory Adapter。"""

import pytest

from nexusmcp.modules.toolsets.adapters.in_memory import InMemoryToolsetCatalogReader
from nexusmcp.modules.toolsets.domain import ToolsetMemberAvailability
from nexusmcp.modules.toolsets.ports import ToolsetCatalogSnapshot


@pytest.mark.asyncio
async def test_catalog_reader_preserves_requested_order_and_tenant_scope() -> None:
    tool_a = ToolsetCatalogSnapshot(
        tool_id="tool-a",
        tenant_id="tenant-a",
        availability=ToolsetMemberAvailability.AVAILABLE,
        published_tool_version_id="tool-a-v1",
    )
    tool_b = ToolsetCatalogSnapshot(
        tool_id="tool-b",
        tenant_id="tenant-a",
        availability=ToolsetMemberAvailability.TOOL_DISABLED,
        published_tool_version_id=None,
    )
    reader = InMemoryToolsetCatalogReader((tool_a, tool_b))

    assert await reader.list_member_snapshots(
        "tenant-a",
        ("tool-b", "missing", "tool-a"),
    ) == (tool_b, tool_a)
    assert await reader.list_member_snapshots("tenant-b", ("tool-a",)) == ()
    assert await reader.list_published_snapshots("tenant-a") == (tool_a,)


def test_catalog_snapshot_requires_version_only_when_available() -> None:
    with pytest.raises(ValueError, match="requires published version"):
        ToolsetCatalogSnapshot(
            tool_id="tool-a",
            tenant_id="tenant-a",
            availability=ToolsetMemberAvailability.AVAILABLE,
            published_tool_version_id=None,
        )
    with pytest.raises(ValueError, match="must not expose"):
        ToolsetCatalogSnapshot(
            tool_id="tool-a",
            tenant_id="tenant-a",
            availability=ToolsetMemberAvailability.NO_PUBLISHED_VERSION,
            published_tool_version_id="unexpected-version",
        )
