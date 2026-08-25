"""ToolBinding 生命周期不变量测试。"""

from datetime import UTC, datetime

import pytest

from nexusmcp.modules.connectors.domain import (
    ToolBinding,
    ToolBindingStatus,
    ToolBindingType,
)

NOW = datetime(2026, 8, 25, tzinfo=UTC)


def _draft_binding() -> ToolBinding:
    return ToolBinding(
        id="binding-1",
        tenant_id="tenant-a",
        tool_version_id="version-1",
        upstream_service_id="upstream-1",
        imported_operation_id=None,
        binding_type=ToolBindingType.HTTP,
        binding_config={"method": "GET", "path_template": "/employees/{employee_id}"},
        binding_digest="binding-v1",
        status=ToolBindingStatus.DRAFT,
        created_at=NOW,
    )


def test_tool_binding_must_publish_before_it_can_be_disabled() -> None:
    draft = _draft_binding()

    with pytest.raises(ValueError, match="only published"):
        draft.disable()

    published = draft.publish(NOW)
    disabled = published.disable()

    assert published.status is ToolBindingStatus.PUBLISHED
    assert disabled.status is ToolBindingStatus.DISABLED
    assert disabled.published_at == NOW
