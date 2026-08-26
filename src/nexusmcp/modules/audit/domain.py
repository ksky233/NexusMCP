"""脱敏、追加式 Audit Event 契约。"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class AuditAction(StrEnum):
    TOOL_CALL = "tool_call"
    APPROVAL_DECISION = "approval_decision"
    CREDENTIAL_RESOLUTION = "credential_resolution"


class AuditOutcome(StrEnum):
    ALLOWED = "allowed"
    DENIED = "denied"
    APPROVAL_REQUIRED = "approval_required"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    UNKNOWN = "unknown"
    CANCELLED = "cancelled"


type AuditMetadataValue = str | int | float | bool | None


@dataclass(frozen=True, slots=True)
class AuditEvent:
    id: str
    tenant_id: str
    actor_id: str
    action: AuditAction
    resource_type: str
    resource_id: str
    outcome: AuditOutcome
    request_id: str
    trace_id: str
    occurred_at: datetime
    arguments_digest: str | None = None
    policy_version: str | None = None
    reason_code: str | None = None
    execution_id: str | None = None
    metadata: Mapping[str, AuditMetadataValue] | None = None

    def __post_init__(self) -> None:
        if self.metadata is None:
            return
        sensitive_keys = {
            "api_key",
            "arguments",
            "authorization",
            "cookie",
            "password",
            "result",
            "secret",
            "token",
        }
        normalized_keys = {str(key).strip().lower().replace("-", "_") for key in self.metadata}
        if normalized_keys & sensitive_keys:
            raise ValueError("audit metadata must not contain sensitive fields")
