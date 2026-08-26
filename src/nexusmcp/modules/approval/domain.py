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
        if self.status is ApprovalStatus.CONSUMED and (
            self.decided_by is None or self.decided_at is None or self.consumed_at is None
        ):
            raise ValueError("consumed approval must contain decision and consume state")

    def approve(self, approver_id: str, decided_at: datetime) -> ApprovalRequest:
        self._require_pending(decided_at)
        return replace(
            self,
            status=ApprovalStatus.APPROVED,
            decided_by=approver_id,
            decided_at=decided_at,
        )

    def reject(self, approver_id: str, decided_at: datetime) -> ApprovalRequest:
        self._require_pending(decided_at)
        return replace(
            self,
            status=ApprovalStatus.REJECTED,
            decided_by=approver_id,
            decided_at=decided_at,
        )

    def expire(self, expired_at: datetime) -> ApprovalRequest:
        if self.status is not ApprovalStatus.PENDING:
            raise ValueError("only pending approval can expire")
        if expired_at < self.expires_at:
            raise ValueError("approval cannot expire before expires_at")
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
