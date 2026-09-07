"""Admin Query 专用 Read Model；不承担领域状态变更。"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class Page[T]:
    items: tuple[T, ...]
    offset: int
    limit: int
    total: int


@dataclass(frozen=True, slots=True)
class SearchProjectionSummary:
    published_tools: int
    indexed_tools: int
    pending_tools: int
    coverage_percent: float
    embedding_model: str
    embedding_dimensions: int
    latest_indexed_at: datetime | None


@dataclass(frozen=True, slots=True)
class DashboardSummary:
    active_upstreams: int
    published_tools: int
    pending_reviews: int
    pending_approvals: int
    failed_executions: int
    unknown_executions: int
    search_projection: SearchProjectionSummary


@dataclass(frozen=True, slots=True)
class UpstreamDetail:
    id: str
    tenant_id: str
    namespace: str
    name: str
    description: str | None
    owner: str
    service_type: str
    transport_type: str
    endpoint: str
    protocol_min: str | None
    protocol_max: str | None
    auth_scheme: str | None
    config: Mapping[str, Any]
    status: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class ImportJobSummary:
    id: str
    upstream_service_id: str
    upstream_name: str
    source_type: str
    source_ref: str
    source_digest: str
    openapi_version: str | None
    status: str
    error_summary: str | None
    created_by: str
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None


@dataclass(frozen=True, slots=True)
class ReviewOperationSummary:
    id: str
    import_job_id: str
    upstream_service_id: str
    operation_id: str | None
    operation_key: str
    method: str
    path: str
    generated_tool_name: str | None
    conflict_status: str
    review_status: str
    review_notes: str | None
    draft_tool_version_id: str | None
    draft_tool_binding_id: str | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class ToolSummary:
    id: str
    namespace: str
    canonical_name: str
    owner: str
    status: str
    latest_version_id: str
    latest_version: int
    display_name: str
    description: str
    version_status: str
    visibility: str
    side_effect: str
    tags: tuple[str, ...]
    upstream_service_id: str | None
    upstream_name: str | None
    upstream_namespace: str | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class ToolVersionDetail:
    id: str
    tool_id: str
    version: int
    display_name: str
    description: str
    input_schema: Mapping[str, Any]
    output_schema: Mapping[str, Any] | None
    schema_digest: str
    tags: tuple[str, ...]
    side_effect: str
    visibility: str
    status: str
    created_by: str
    created_at: datetime
    reviewed_at: datetime | None
    published_at: datetime | None
    retired_at: datetime | None


@dataclass(frozen=True, slots=True)
class ToolDetail:
    id: str
    tenant_id: str
    namespace: str
    canonical_name: str
    owner: str
    status: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class ToolBindingDetail:
    id: str
    tool_version_id: str
    upstream_service_id: str
    imported_operation_id: str | None
    binding_type: str
    binding_config: Mapping[str, Any]
    binding_digest: str
    status: str
    created_at: datetime
    updated_at: datetime
    published_at: datetime | None


@dataclass(frozen=True, slots=True)
class ApprovalSummary:
    id: str
    principal_id: str
    tool_id: str
    tool_version_id: str
    canonical_name: str
    arguments_digest: str
    policy_version: str
    has_idempotency_key: bool
    status: str
    requested_at: datetime
    expires_at: datetime
    decided_by: str | None
    decided_at: datetime | None
    consumed_at: datetime | None


@dataclass(frozen=True, slots=True)
class ExecutionSummary:
    id: str
    request_id: str
    trace_id: str
    principal_id: str
    tool_id: str
    tool_version_id: str
    tool_binding_id: str
    canonical_name: str
    policy_version: str
    policy_reason_code: str
    side_effect: str
    status: str
    has_idempotency_key: bool
    planned_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    error_code: str | None
    error_category: str | None
    attempt_count: int
    mcp_scope_type: str
    toolset_id: str | None
    toolset_revision: int | None


@dataclass(frozen=True, slots=True)
class ExecutionAttemptSummary:
    id: str
    execution_id: str
    attempt_number: int
    status: str
    started_at: datetime
    finished_at: datetime | None
    error_code: str | None
    error_category: str | None
    upstream_status: int | None


@dataclass(frozen=True, slots=True)
class AuditEventSummary:
    id: str
    actor_id: str
    action: str
    resource_type: str
    resource_id: str
    outcome: str
    request_id: str
    trace_id: str
    occurred_at: datetime
    arguments_digest: str | None
    policy_version: str | None
    reason_code: str | None
    execution_id: str | None
    metadata: Mapping[str, str | int | float | bool | None]
