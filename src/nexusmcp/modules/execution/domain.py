"""Tool Call、Execution 状态、错误分类与 Retry 决策模型。"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
from typing import Any

from nexusmcp.modules.catalog.domain import ToolSideEffect, ToolVisibility
from nexusmcp.modules.connectors.domain import ToolBindingType
from nexusmcp.shared.digests import canonical_json_digest
from nexusmcp.shared.request_context import ActorContext


class ExecutionStatus(StrEnum):
    PLANNED = "planned"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    UNKNOWN = "unknown"
    CANCELLED = "cancelled"


class ExecutionErrorCategory(StrEnum):
    VALIDATION = "validation"
    AUTHENTICATION = "authentication"
    AUTHORIZATION = "authorization"
    APPROVAL = "approval"
    CREDENTIAL = "credential"
    TIMEOUT_BEFORE_SEND = "timeout_before_send"
    TIMEOUT_AFTER_SEND = "timeout_after_send"
    NETWORK = "network"
    UPSTREAM_4XX = "upstream_4xx"
    UPSTREAM_5XX = "upstream_5xx"
    CANCELLED = "cancelled"
    UNKNOWN = "unknown"


class RetryDisposition(StrEnum):
    RETRY = "retry"
    DO_NOT_RETRY = "do_not_retry"
    REQUIRE_RECONCILIATION = "require_reconciliation"


@dataclass(frozen=True, slots=True)
class CallToolCommand:
    context: ActorContext
    tool_name: str
    arguments: Mapping[str, Any]
    idempotency_key: str | None = None
    approval_id: str | None = None

    def __post_init__(self) -> None:
        if not self.tool_name.strip():
            raise ValueError("tool name must not be blank")

    @property
    def arguments_digest(self) -> str:
        return canonical_json_digest(dict(self.arguments))


@dataclass(frozen=True, slots=True)
class ResolvedExecutableTool:
    tenant_id: str
    tool_id: str
    tool_version_id: str
    tool_binding_id: str
    upstream_service_id: str
    canonical_name: str
    version: int
    input_schema: Mapping[str, Any]
    output_schema: Mapping[str, Any] | None
    side_effect: ToolSideEffect
    visibility: ToolVisibility
    binding_type: ToolBindingType
    binding_config: Mapping[str, Any]
    upstream_endpoint: str
    upstream_auth_scheme: str | None


@dataclass(frozen=True, slots=True)
class ToolExecution:
    id: str
    tenant_id: str
    request_id: str
    trace_id: str
    principal_id: str
    tool_id: str
    tool_version_id: str
    tool_binding_id: str
    arguments_digest: str
    policy_version: str
    policy_reason_code: str
    side_effect: ToolSideEffect
    status: ExecutionStatus
    planned_at: datetime
    approval_id: str | None = None
    credential_binding_id: str | None = None
    idempotency_key: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error_code: str | None = None
    error_category: ExecutionErrorCategory | None = None

    def __post_init__(self) -> None:
        for field_name, value in (
            ("execution id", self.id),
            ("tenant id", self.tenant_id),
            ("request id", self.request_id),
            ("trace id", self.trace_id),
            ("principal id", self.principal_id),
            ("tool id", self.tool_id),
            ("tool version id", self.tool_version_id),
            ("tool binding id", self.tool_binding_id),
            ("arguments digest", self.arguments_digest),
            ("policy version", self.policy_version),
            ("policy reason code", self.policy_reason_code),
        ):
            if not value.strip():
                raise ValueError(f"{field_name} must not be blank")
        if self.status is ExecutionStatus.PLANNED and (
            self.started_at is not None or self.finished_at is not None
        ):
            raise ValueError("planned execution must not have start or finish time")
        if self.status is ExecutionStatus.RUNNING and self.started_at is None:
            raise ValueError("running execution must have started_at")
        if (
            self.status
            in {
                ExecutionStatus.SUCCEEDED,
                ExecutionStatus.FAILED,
                ExecutionStatus.UNKNOWN,
                ExecutionStatus.CANCELLED,
            }
            and self.finished_at is None
        ):
            raise ValueError("terminal execution must have finished_at")
        if self.status in (ExecutionStatus.PLANNED, ExecutionStatus.RUNNING) and (
            self.error_code is not None or self.error_category is not None
        ):
            raise ValueError("non-terminal execution must not have error state")
        if self.status is ExecutionStatus.SUCCEEDED and (
            self.error_code is not None or self.error_category is not None
        ):
            raise ValueError("succeeded execution must not have error state")
        if self.status in {
            ExecutionStatus.FAILED,
            ExecutionStatus.UNKNOWN,
            ExecutionStatus.CANCELLED,
        } and (self.error_code is None or self.error_category is None):
            raise ValueError("unsuccessful terminal execution must contain error state")

    def start(self, started_at: datetime) -> ToolExecution:
        if self.status is not ExecutionStatus.PLANNED:
            raise ValueError("only planned execution can start")
        return replace(self, status=ExecutionStatus.RUNNING, started_at=started_at)

    def succeed(self, finished_at: datetime) -> ToolExecution:
        self._require_running()
        return replace(self, status=ExecutionStatus.SUCCEEDED, finished_at=finished_at)

    def fail(
        self,
        *,
        error_code: str,
        category: ExecutionErrorCategory,
        finished_at: datetime,
    ) -> ToolExecution:
        self._require_running()
        return replace(
            self,
            status=ExecutionStatus.FAILED,
            error_code=error_code,
            error_category=category,
            finished_at=finished_at,
        )

    def mark_unknown(
        self,
        *,
        error_code: str,
        finished_at: datetime,
    ) -> ToolExecution:
        self._require_running()
        return replace(
            self,
            status=ExecutionStatus.UNKNOWN,
            error_code=error_code,
            error_category=ExecutionErrorCategory.UNKNOWN,
            finished_at=finished_at,
        )

    def cancel(self, finished_at: datetime) -> ToolExecution:
        if self.status not in (ExecutionStatus.PLANNED, ExecutionStatus.RUNNING):
            raise ValueError("only planned or running execution can be cancelled")
        return replace(
            self,
            status=ExecutionStatus.CANCELLED,
            error_code="execution_cancelled",
            error_category=ExecutionErrorCategory.CANCELLED,
            finished_at=finished_at,
        )

    def _require_running(self) -> None:
        if self.status is not ExecutionStatus.RUNNING:
            raise ValueError("execution must be running before terminal transition")


@dataclass(frozen=True, slots=True)
class ExecutorRequest:
    execution_id: str
    tool: ResolvedExecutableTool
    arguments: Mapping[str, Any]
    timeout_seconds: float

    def __post_init__(self) -> None:
        if self.timeout_seconds <= 0:
            raise ValueError("executor timeout must be positive")


@dataclass(frozen=True, slots=True)
class ExecutorResult:
    data: Any
    content_type: str | None
    upstream_status: int | None


@dataclass(frozen=True, slots=True)
class CallToolResult:
    execution_id: str
    data: Any
    content_type: str | None
    upstream_status: int | None


class ExecutorFailure(Exception):
    def __init__(
        self,
        *,
        code: str,
        category: ExecutionErrorCategory,
        outcome_unknown: bool = False,
    ) -> None:
        super().__init__(code)
        self.code = code
        self.category = category
        self.outcome_unknown = outcome_unknown


def retry_disposition(
    *,
    side_effect: ToolSideEffect,
    error_category: ExecutionErrorCategory,
    has_idempotency_key: bool,
) -> RetryDisposition:
    if error_category in {
        ExecutionErrorCategory.VALIDATION,
        ExecutionErrorCategory.AUTHENTICATION,
        ExecutionErrorCategory.AUTHORIZATION,
        ExecutionErrorCategory.APPROVAL,
        ExecutionErrorCategory.CREDENTIAL,
        ExecutionErrorCategory.UPSTREAM_4XX,
        ExecutionErrorCategory.CANCELLED,
    }:
        return RetryDisposition.DO_NOT_RETRY
    if error_category in {
        ExecutionErrorCategory.TIMEOUT_AFTER_SEND,
        ExecutionErrorCategory.UNKNOWN,
    } and side_effect in {
        ToolSideEffect.NON_IDEMPOTENT_WRITE,
        ToolSideEffect.UNKNOWN,
    }:
        return RetryDisposition.REQUIRE_RECONCILIATION
    retryable_transport_error = error_category in {
        ExecutionErrorCategory.TIMEOUT_BEFORE_SEND,
        ExecutionErrorCategory.TIMEOUT_AFTER_SEND,
        ExecutionErrorCategory.NETWORK,
        ExecutionErrorCategory.UPSTREAM_5XX,
        ExecutionErrorCategory.UNKNOWN,
    }
    if not retryable_transport_error:
        return RetryDisposition.DO_NOT_RETRY
    if side_effect is ToolSideEffect.READ_ONLY:
        return RetryDisposition.RETRY
    if side_effect is ToolSideEffect.IDEMPOTENT_WRITE and has_idempotency_key:
        return RetryDisposition.RETRY
    return RetryDisposition.DO_NOT_RETRY
