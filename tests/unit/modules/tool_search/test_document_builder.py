"""Canonical Tool Search Document 的确定性、摘要与字段提取测试。"""

from dataclasses import replace

from nexusmcp.modules.catalog.domain import PublishedTool, ToolSideEffect, ToolVisibility
from nexusmcp.modules.tool_search.document_builder import ToolSearchDocumentBuilder


def tool() -> PublishedTool:
    return PublishedTool(
        tool_id="tool-1",
        tool_version_id="version-1",
        tenant_id="tenant-a",
        canonical_name="inventory.set_reorder_level",
        display_name="Set   reorder level",
        description="Set the desired\nreorder level for one SKU.",
        input_schema={
            "type": "object",
            "properties": {
                "body": {
                    "type": "object",
                    "properties": {
                        "reorder_level": {"type": "integer"},
                        "warehouse_id": {
                            "type": "string",
                            "description": "Warehouse identifier.",
                        },
                    },
                    "required": ["warehouse_id", "reorder_level"],
                },
                "sku": {"type": "string"},
            },
            "required": ["sku", "body"],
        },
        output_schema=None,
        version=1,
        visibility=ToolVisibility.AUTHENTICATED,
        side_effect=ToolSideEffect.IDEMPOTENT_WRITE,
        schema_digest="1" * 64,
        owner="inventory-platform",
        tags=("write", "inventory", "idempotent"),
    )


def test_builder_creates_stable_normalized_document_and_digest() -> None:
    document = ToolSearchDocumentBuilder().build(tool())

    assert document.content == (
        "Canonical Name: inventory.set_reorder_level\n"
        "Display Name: Set reorder level\n"
        "Namespace: inventory\n"
        "Description: Set the desired reorder level for one SKU.\n"
        "Tags: idempotent, inventory, write\n"
        "Side Effect: idempotent_write\n"
        "Inputs: body.reorder_level (integer, required), "
        "body.warehouse_id (string, required): Warehouse identifier., "
        "sku (string, required)\n"
        "Owner: inventory-platform"
    )
    assert len(document.source_digest) == 64
    assert "properties" not in document.content
    assert ToolSearchDocumentBuilder().build(tool()) == document


def test_semantic_content_change_updates_source_digest() -> None:
    builder = ToolSearchDocumentBuilder()
    original = builder.build(tool())
    updated = builder.build(
        replace(tool(), description="Configure the replenishment trigger threshold.")
    )

    assert updated.source_digest != original.source_digest
