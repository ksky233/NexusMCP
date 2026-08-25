"""Catalog Domain 的身份、版本和投影不变量测试。"""

from datetime import UTC, datetime

import pytest

from nexusmcp.modules.catalog.domain import (
    PublishedTool,
    Tool,
    ToolSideEffect,
    ToolVersion,
    ToolVersionStatus,
    ToolVisibility,
)

NOW = datetime(2026, 8, 25, tzinfo=UTC)


def test_tool_canonical_name_must_belong_to_namespace() -> None:
    with pytest.raises(ValueError, match="must start with its namespace"):
        Tool(
            id="tool-1",
            tenant_id="tenant-a",
            namespace="directory",
            canonical_name="inventory.get_item",
            owner="people-platform",
        )


def test_published_version_requires_publish_timestamp() -> None:
    with pytest.raises(ValueError, match="published_at"):
        ToolVersion(
            id="version-1",
            tenant_id="tenant-a",
            tool_id="tool-1",
            version=1,
            display_name="Get employee",
            description="Get one employee.",
            input_schema={"type": "object", "properties": {}},
            output_schema=None,
            schema_digest="schema-v1",
            tags=("directory",),
            side_effect=ToolSideEffect.READ_ONLY,
            visibility=ToolVisibility.PUBLIC,
            status=ToolVersionStatus.PUBLISHED,
            created_by="reviewer-a",
            created_at=NOW,
            reviewed_at=NOW,
        )


def test_restricted_projection_fails_closed_before_policy_is_available() -> None:
    tool = PublishedTool(
        tool_id="tool-1",
        tool_version_id="version-1",
        tenant_id="tenant-a",
        canonical_name="directory.get_employee",
        display_name="Get employee",
        description="Get one employee.",
        input_schema={"type": "object", "properties": {}},
        output_schema=None,
        version=1,
        visibility=ToolVisibility.RESTRICTED,
        side_effect=ToolSideEffect.READ_ONLY,
        schema_digest="schema-v1",
    )

    assert tool.is_visible_to("operator") is False


def test_tool_version_lifecycle_cannot_skip_review() -> None:
    draft = ToolVersion(
        id="version-1",
        tenant_id="tenant-a",
        tool_id="tool-1",
        version=1,
        display_name="Get employee",
        description="Get one employee.",
        input_schema={"type": "object", "properties": {}},
        output_schema=None,
        schema_digest="schema-v1",
        tags=("directory",),
        side_effect=ToolSideEffect.READ_ONLY,
        visibility=ToolVisibility.PUBLIC,
        status=ToolVersionStatus.DRAFT,
        created_by="reviewer-a",
        created_at=NOW,
    )

    with pytest.raises(ValueError, match="only review"):
        draft.publish(NOW)

    review = draft.submit_for_review(NOW)
    published = review.publish(NOW)
    retired = published.retire(NOW)

    assert review.status is ToolVersionStatus.REVIEW
    assert published.status is ToolVersionStatus.PUBLISHED
    assert retired.status is ToolVersionStatus.RETIRED
