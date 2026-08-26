"""参数摘要绑定、带过期时间且只能消费一次的 Approval。"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum


class ApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    CONSUMED = "consumed"


@dataclass(frozen=True, slots=True)
class ApprovalRequest:
    id: str
    tenant_id: str
    principal_id: str
    tool_id: str
    tool_version_id: str
    arguments_digest: str
    policy_version: str
    status: ApprovalStatus
    requested_at: datetime
    expires_at: datetime
    decided_by: str | None = None
    decided_at: datetime | None = None
    consumed_at: datetime | None = None

    def __post_init__(self) -> None:
        for field_name, value in (
            ("approval id", self.id),
            ("tenant id", self.tenant_id),
            ("principal id", self.principal_id),
            ("tool id", self.tool_id),
            ("tool version id", self.tool_version_id),
            ("arguments digest", self.arguments_digest),
            ("policy version", self.policy_version),
        ):
            if not value.strip():
                raise ValueError(f"{field_name} must not be blank")
        if self.expires_at <= self.requested_at:
            raise ValueError("approval expires_at must be after requested_at")
        if self.status is ApprovalStatus.PENDING and any(
            value is not None for value in (self.decided_by, self.decided_at, self.consumed_at)
        ):
            raise ValueError("pending approval must not contain decision state")
        if self.status in (ApprovalStatus.APPROVED, ApprovalStatus.REJECTED) and (
            self.decided_by is None or self.decided_at is None
        ):
            raise ValueError("decided approval must contain approver and decision time")
        if self.status is ApprovalStatus.EXPIRED and (
            self.decided_by is None or self.decided_at is None
        ):
            raise ValueError("expired approval must contain decision state")
        if self.status is not ApprovalStatus.CONSUMED and self.consumed_at is not None:
            raise ValueError("only consumed approval may contain consumed_at")
        if self.status is ApprovalStatus.CONSUMED and (
            self.decided_by is None or self.decided_at is None or self.consumed_at is None
        ):
            raise ValueError("consumed approval must contain decision and consume state")

    def approve(self, approver_id: str, decided_at: datetime) -> ApprovalRequest:
        if not approver_id.strip():
            raise ValueError("approval approver id must not be blank")
        self._require_pending(decided_at)
        return replace(
            self,
            status=ApprovalStatus.APPROVED,
            decided_by=approver_id,
            decided_at=decided_at,
        )

    def reject(self, approver_id: str, decided_at: datetime) -> ApprovalRequest:
        if not approver_id.strip():
            raise ValueError("approval approver id must not be blank")
        self._require_pending(decided_at)
        return replace(
            self,
            status=ApprovalStatus.REJECTED,
            decided_by=approver_id,
            decided_at=decided_at,
        )

    def expire(self, expired_at: datetime) -> ApprovalRequest:
        if self.status not in (ApprovalStatus.PENDING, ApprovalStatus.APPROVED):
            raise ValueError("only pending or approved approval can expire")
        if expired_at < self.expires_at:
            raise ValueError("approval cannot expire before expires_at")
        if self.status is ApprovalStatus.APPROVED:
            return replace(self, status=ApprovalStatus.EXPIRED)
        return replace(
            self,
            status=ApprovalStatus.EXPIRED,
            decided_by="system",
            decided_at=expired_at,
        )

    def consume(
        self,
        *,
        principal_id: str,
        tool_version_id: str,
        arguments_digest: str,
        policy_version: str,
        consumed_at: datetime,
    ) -> ApprovalRequest:
        if self.status is not ApprovalStatus.APPROVED:
            raise ValueError("only approved approval can be consumed")
        if consumed_at >= self.expires_at:
            raise ValueError("expired approval cannot be consumed")
        if principal_id != self.principal_id:
            raise ValueError("approval principal does not match call principal")
        if tool_version_id != self.tool_version_id:
            raise ValueError("approval tool version does not match call version")
        if arguments_digest != self.arguments_digest:
            raise ValueError("approval arguments digest does not match call arguments")
        if policy_version != self.policy_version:
            raise ValueError("approval policy version does not match current policy")
        return replace(
            self,
            status=ApprovalStatus.CONSUMED,
            consumed_at=consumed_at,
        )

    def _require_pending(self, decided_at: datetime) -> None:
        if self.status is not ApprovalStatus.PENDING:
            raise ValueError("only pending approval can be decided")
        if decided_at >= self.expires_at:
            raise ValueError("expired approval cannot be decided")
