"""Audit Event 只保存摘要和脱敏元数据的结构测试。"""

from datetime import UTC, datetime

import pytest

from nexusmcp.modules.audit.domain import AuditAction, AuditEvent, AuditOutcome


def test_audit_event_has_digest_but_no_raw_arguments_or_secret_fields() -> None:
    event = AuditEvent(
        id="audit-1",
        tenant_id="tenant-a",
        actor_id="agent-service-a",
        action=AuditAction.TOOL_CALL,
        resource_type="tool_version",
        resource_id="version-1",
        outcome=AuditOutcome.SUCCEEDED,
        request_id="request-1",
        trace_id="a" * 32,
        occurred_at=datetime(2026, 8, 26, tzinfo=UTC),
        arguments_digest="1" * 64,
        metadata={"side_effect": "read_only"},
    )

    fields = event.__dataclass_fields__
    assert event.arguments_digest == "1" * 64
    assert "arguments" not in fields
    assert "result" not in fields
    assert "secret" not in fields


def test_audit_metadata_rejects_sensitive_keys() -> None:
    with pytest.raises(ValueError, match="sensitive"):
        AuditEvent(
            id="audit-2",
            tenant_id="tenant-a",
            actor_id="agent-service-a",
            action=AuditAction.TOOL_CALL,
            resource_type="tool_version",
            resource_id="version-1",
            outcome=AuditOutcome.FAILED,
            request_id="request-2",
            trace_id="b" * 32,
            occurred_at=datetime(2026, 8, 26, tzinfo=UTC),
            metadata={"authorization": "Bearer must-not-exist"},
        )
