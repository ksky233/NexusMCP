"""FTS Search Snapshot 字段构建测试。"""

from datetime import UTC, datetime

from nexusmcp.modules.catalog.adapters.sqlalchemy_mapping import tool_version_search_fields
from nexusmcp.modules.catalog.domain import (
    ToolSideEffect,
    ToolVersion,
    ToolVersionStatus,
    ToolVisibility,
)


def test_search_snapshot_separates_name_tags_and_description_weights() -> None:
    version = ToolVersion(
        id="version-1",
        tenant_id="tenant-a",
        tool_id="tool-1",
        version=1,
        display_name="Reserve stock",
        description="Create a reservation for one warehouse order.",
        input_schema={"type": "object", "properties": {}},
        output_schema=None,
        schema_digest="1" * 64,
        tags=("inventory", "write"),
        side_effect=ToolSideEffect.NON_IDEMPOTENT_WRITE,
        visibility=ToolVisibility.PUBLIC,
        status=ToolVersionStatus.DRAFT,
        created_by="reviewer",
        created_at=datetime(2026, 8, 26, tzinfo=UTC),
    )

    search_name, search_tags, search_description = tool_version_search_fields(
        version,
        namespace="inventory",
        canonical_name="inventory.reserve_stock",
    )

    assert search_name == "inventory inventory.reserve_stock Reserve stock"
    assert search_tags == "inventory write"
    assert search_description == version.description
