"""Schema/Binding Canonical JSON Digest 测试。"""

from dataclasses import replace
from datetime import UTC, datetime

from nexusmcp.modules.catalog.digests import calculate_schema_digest
from nexusmcp.modules.connectors.digests import calculate_binding_digest
from nexusmcp.modules.connectors.domain import (
    ToolBinding,
    ToolBindingStatus,
    ToolBindingType,
)


def _binding(config: dict[str, object]) -> ToolBinding:
    return ToolBinding(
        id="binding-1",
        tenant_id="tenant-a",
        tool_version_id="version-1",
        upstream_service_id="upstream-1",
        imported_operation_id=None,
        binding_type=ToolBindingType.HTTP,
        binding_config=config,
        binding_digest="pending",
        status=ToolBindingStatus.DRAFT,
        created_at=datetime(2026, 8, 25, tzinfo=UTC),
    )


def test_schema_digest_is_stable_across_mapping_key_order() -> None:
    first = calculate_schema_digest(
        {"type": "object", "properties": {"id": {"type": "string"}}},
        None,
    )
    second = calculate_schema_digest(
        {"properties": {"id": {"type": "string"}}, "type": "object"},
        None,
    )

    assert first == second
    assert len(first) == 64


def test_binding_digest_changes_when_execution_semantics_change() -> None:
    original = _binding({"method": "GET", "path_template": "/employees/{id}"})
    changed = replace(
        original,
        binding_config={"method": "DELETE", "path_template": "/employees/{id}"},
    )

    assert calculate_binding_digest(original) != calculate_binding_digest(changed)
