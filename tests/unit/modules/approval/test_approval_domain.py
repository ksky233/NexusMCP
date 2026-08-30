"""Approval 参数绑定、过期和单次消费测试。"""

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from nexusmcp.modules.approval.domain import ApprovalRequest, ApprovalStatus

NOW = datetime(2026, 8, 26, 12, 0, tzinfo=UTC)


def _pending() -> ApprovalRequest:
    return ApprovalRequest(
        id="approval-1",
        tenant_id="tenant-a",
        principal_id="agent-service-a",
        tool_id="tool-1",
        tool_version_id="version-1",
        arguments_digest="1" * 64,
        policy_version="policy-v1",
        status=ApprovalStatus.PENDING,
        requested_at=NOW,
        expires_at=NOW + timedelta(minutes=10),
    )


def test_approved_request_can_be_consumed_exactly_once() -> None:
    approved = _pending().approve("approver-a", NOW + timedelta(minutes=1))
    consumed = approved.consume(
        principal_id="agent-service-a",
        tool_version_id="version-1",
        arguments_digest="1" * 64,
        policy_version="policy-v1",
        idempotency_key=None,
        consumed_at=NOW + timedelta(minutes=2),
    )

    assert consumed.status is ApprovalStatus.CONSUMED
    with pytest.raises(ValueError, match="only approved"):
        consumed.consume(
            principal_id="agent-service-a",
            tool_version_id="version-1",
            arguments_digest="1" * 64,
            policy_version="policy-v1",
            idempotency_key=None,
            consumed_at=NOW + timedelta(minutes=3),
        )


@pytest.mark.parametrize(
    ("principal_id", "version_id", "digest", "policy_version"),
    [
        ("agent-service-b", "version-1", "1" * 64, "policy-v1"),
        ("agent-service-a", "version-2", "1" * 64, "policy-v1"),
        ("agent-service-a", "version-1", "2" * 64, "policy-v1"),
        ("agent-service-a", "version-1", "1" * 64, "policy-v2"),
    ],
)
def test_approval_rejects_changed_call_snapshot(
    principal_id: str,
    version_id: str,
    digest: str,
    policy_version: str,
) -> None:
    approved = _pending().approve("approver-a", NOW + timedelta(minutes=1))

    with pytest.raises(ValueError, match="does not match"):
        approved.consume(
            principal_id=principal_id,
            tool_version_id=version_id,
            arguments_digest=digest,
            policy_version=policy_version,
            idempotency_key=None,
            consumed_at=NOW + timedelta(minutes=2),
        )


def test_expired_approval_cannot_be_decided_or_consumed() -> None:
    pending = _pending()

    with pytest.raises(ValueError, match="expired"):
        pending.approve("approver-a", pending.expires_at)
    assert pending.expire(pending.expires_at).status is ApprovalStatus.EXPIRED


def test_approval_rejects_changed_idempotency_key() -> None:
    approved = replace(_pending(), idempotency_key="write-key-1").approve(
        "approver-a",
        NOW + timedelta(minutes=1),
    )

    with pytest.raises(ValueError, match="idempotency key"):
        approved.consume(
            principal_id="agent-service-a",
            tool_version_id="version-1",
            arguments_digest="1" * 64,
            policy_version="policy-v1",
            idempotency_key="write-key-2",
            consumed_at=NOW + timedelta(minutes=2),
        )


def test_approval_cannot_be_constructed_with_incomplete_decision_state() -> None:
    with pytest.raises(ValueError, match="decision"):
        ApprovalRequest(
            id="approval-invalid",
            tenant_id="tenant-a",
            principal_id="agent-service-a",
            tool_id="tool-1",
            tool_version_id="version-1",
            arguments_digest="1" * 64,
            policy_version="policy-v1",
            status=ApprovalStatus.APPROVED,
            requested_at=NOW,
            expires_at=NOW + timedelta(minutes=10),
        )
