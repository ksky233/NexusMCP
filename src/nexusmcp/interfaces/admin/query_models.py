"""W1 Admin Query 的稳定 HTTP Response Contract。"""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict


class AdminReadModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")


class PageMetadata(AdminReadModel):
    offset: int
    limit: int
    total: int


class SearchProjectionResponse(AdminReadModel):
    published_tools: int
    indexed_tools: int
    pending_tools: int
    coverage_percent: float
    embedding_model: str
    embedding_dimensions: int
    latest_indexed_at: datetime | None


class DashboardResponse(AdminReadModel):
    active_upstreams: int
    published_tools: int
    pending_reviews: int
    pending_approvals: int
    failed_executions: int
    unknown_executions: int
    search_projection: SearchProjectionResponse


class UpstreamDetailResponse(AdminReadModel):
    id: str
    tenant_id: str
    namespace: str
    name: str
    description: str | None
    owner: str
    service_type: Literal["http"]
    transport_type: Literal["http"]
    endpoint: str
    protocol_min: str | None
    protocol_max: str | None
    auth_scheme: str | None
    config: dict[str, Any]
    status: str
    created_at: datetime
    updated_at: datetime


class ImportJobSummaryResponse(AdminReadModel):
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


class ImportJobPageResponse(AdminReadModel):
    items: list[ImportJobSummaryResponse]
    page: PageMetadata


class ReviewOperationSummaryResponse(AdminReadModel):
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


class ReviewOperationPageResponse(AdminReadModel):
    items: list[ReviewOperationSummaryResponse]
    page: PageMetadata


class ToolSummaryResponse(AdminReadModel):
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
    tags: list[str]
    upstream_service_id: str | None
    upstream_name: str | None
    upstream_namespace: str | None
    created_at: datetime
    updated_at: datetime


class ToolPageResponse(AdminReadModel):
    items: list[ToolSummaryResponse]
    page: PageMetadata


class ToolDetailResponse(AdminReadModel):
    id: str
    tenant_id: str
    namespace: str
    canonical_name: str
    owner: str
    status: str
    created_at: datetime
    updated_at: datetime


class ToolVersionDetailResponse(AdminReadModel):
    id: str
    tool_id: str
    version: int
    display_name: str
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any] | None
    schema_digest: str
    tags: list[str]
    side_effect: str
    visibility: str
    status: str
    created_by: str
    created_at: datetime
    reviewed_at: datetime | None
    published_at: datetime | None
    retired_at: datetime | None


class ToolVersionPageResponse(AdminReadModel):
    items: list[ToolVersionDetailResponse]
    page: PageMetadata


class ToolBindingDetailResponse(AdminReadModel):
    id: str
    tool_version_id: str
    upstream_service_id: str
    imported_operation_id: str | None
    binding_type: Literal["http"]
    binding_config: dict[str, Any]
    binding_digest: str
    status: str
    created_at: datetime
    updated_at: datetime
    published_at: datetime | None


class ApprovalSummaryResponse(AdminReadModel):
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


class ApprovalPageResponse(AdminReadModel):
    items: list[ApprovalSummaryResponse]
    page: PageMetadata


class ExecutionSummaryResponse(AdminReadModel):
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
    mcp_scope_type: Literal["root", "toolset"]
    toolset_id: str | None
    toolset_revision: int | None


class ExecutionPageResponse(AdminReadModel):
    items: list[ExecutionSummaryResponse]
    page: PageMetadata


class ExecutionAttemptResponse(AdminReadModel):
    id: str
    execution_id: str
    attempt_number: int
    status: str
    started_at: datetime
    finished_at: datetime | None
    error_code: str | None
    error_category: str | None
    upstream_status: int | None


class ExecutionAttemptPageResponse(AdminReadModel):
    items: list[ExecutionAttemptResponse]
    page: PageMetadata


class AuditEventResponse(AdminReadModel):
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
    metadata: dict[str, str | int | float | bool | None]


class AuditEventPageResponse(AdminReadModel):
    items: list[AuditEventResponse]
    page: PageMetadata
