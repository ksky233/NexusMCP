"""Execution Domain 与 ORM Model 的显式映射。"""

from nexusmcp.infrastructure.persistence.identifiers import as_uuid
from nexusmcp.modules.catalog.domain import ToolSideEffect
from nexusmcp.modules.execution.adapters.sqlalchemy_models import (
    ExecutionAttemptModel,
    ToolExecutionModel,
)
from nexusmcp.modules.execution.domain import (
    ExecutionAttempt,
    ExecutionAttemptStatus,
    ExecutionErrorCategory,
    ExecutionStatus,
    McpScopeType,
    ToolExecution,
)


def execution_to_model(execution: ToolExecution) -> ToolExecutionModel:
    return ToolExecutionModel(
        id=as_uuid(execution.id, field_name="execution id"),
        tenant_id=as_uuid(execution.tenant_id, field_name="tenant id"),
        request_id=execution.request_id,
        trace_id=execution.trace_id,
        principal_id=execution.principal_id,
        tool_id=as_uuid(execution.tool_id, field_name="tool id"),
        tool_version_id=as_uuid(execution.tool_version_id, field_name="tool version id"),
        tool_binding_id=as_uuid(execution.tool_binding_id, field_name="tool binding id"),
        mcp_scope_type=execution.mcp_scope_type.value,
        toolset_id=(
            as_uuid(execution.toolset_id, field_name="toolset id")
            if execution.toolset_id is not None
            else None
        ),
        toolset_revision=execution.toolset_revision,
        approval_id=(
            as_uuid(execution.approval_id, field_name="approval id")
            if execution.approval_id is not None
            else None
        ),
        credential_binding_id=execution.credential_binding_id,
        arguments_digest=execution.arguments_digest,
        policy_version=execution.policy_version,
        policy_reason_code=execution.policy_reason_code,
        side_effect=execution.side_effect.value,
        status=execution.status.value,
        idempotency_key=execution.idempotency_key,
        planned_at=execution.planned_at,
        started_at=execution.started_at,
        finished_at=execution.finished_at,
        error_code=execution.error_code,
        error_category=(
            execution.error_category.value if execution.error_category is not None else None
        ),
        attempt_count=execution.attempt_count,
    )


def execution_from_model(model: ToolExecutionModel) -> ToolExecution:
    return ToolExecution(
        id=str(model.id),
        tenant_id=str(model.tenant_id),
        request_id=model.request_id,
        trace_id=model.trace_id,
        principal_id=model.principal_id,
        tool_id=str(model.tool_id),
        tool_version_id=str(model.tool_version_id),
        tool_binding_id=str(model.tool_binding_id),
        mcp_scope_type=McpScopeType(model.mcp_scope_type),
        toolset_id=str(model.toolset_id) if model.toolset_id is not None else None,
        toolset_revision=model.toolset_revision,
        approval_id=str(model.approval_id) if model.approval_id is not None else None,
        credential_binding_id=model.credential_binding_id,
        arguments_digest=model.arguments_digest,
        policy_version=model.policy_version,
        policy_reason_code=model.policy_reason_code,
        side_effect=ToolSideEffect(model.side_effect),
        status=ExecutionStatus(model.status),
        idempotency_key=model.idempotency_key,
        planned_at=model.planned_at,
        started_at=model.started_at,
        finished_at=model.finished_at,
        error_code=model.error_code,
        error_category=(
            ExecutionErrorCategory(model.error_category)
            if model.error_category is not None
            else None
        ),
        attempt_count=model.attempt_count,
    )


def update_execution_model(model: ToolExecutionModel, execution: ToolExecution) -> None:
    model.status = execution.status.value
    model.started_at = execution.started_at
    model.finished_at = execution.finished_at
    model.error_code = execution.error_code
    model.error_category = (
        execution.error_category.value if execution.error_category is not None else None
    )
    model.attempt_count = execution.attempt_count


def attempt_to_model(attempt: ExecutionAttempt) -> ExecutionAttemptModel:
    return ExecutionAttemptModel(
        id=as_uuid(attempt.id, field_name="execution attempt id"),
        tenant_id=as_uuid(attempt.tenant_id, field_name="tenant id"),
        execution_id=as_uuid(attempt.execution_id, field_name="execution id"),
        attempt_number=attempt.attempt_number,
        status=attempt.status.value,
        started_at=attempt.started_at,
        finished_at=attempt.finished_at,
        error_code=attempt.error_code,
        error_category=(
            attempt.error_category.value if attempt.error_category is not None else None
        ),
        upstream_status=attempt.upstream_status,
    )


def attempt_from_model(model: ExecutionAttemptModel) -> ExecutionAttempt:
    return ExecutionAttempt(
        id=str(model.id),
        tenant_id=str(model.tenant_id),
        execution_id=str(model.execution_id),
        attempt_number=model.attempt_number,
        status=ExecutionAttemptStatus(model.status),
        started_at=model.started_at,
        finished_at=model.finished_at,
        error_code=model.error_code,
        error_category=(
            ExecutionErrorCategory(model.error_category)
            if model.error_category is not None
            else None
        ),
        upstream_status=model.upstream_status,
    )


def update_attempt_model(model: ExecutionAttemptModel, attempt: ExecutionAttempt) -> None:
    model.status = attempt.status.value
    model.finished_at = attempt.finished_at
    model.error_code = attempt.error_code
    model.error_category = (
        attempt.error_category.value if attempt.error_category is not None else None
    )
    model.upstream_status = attempt.upstream_status
