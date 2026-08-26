"""Execution Domain 与 ORM Model 的显式映射。"""

from nexusmcp.infrastructure.persistence.identifiers import as_uuid
from nexusmcp.modules.catalog.domain import ToolSideEffect
from nexusmcp.modules.execution.adapters.sqlalchemy_models import ToolExecutionModel
from nexusmcp.modules.execution.domain import (
    ExecutionErrorCategory,
    ExecutionStatus,
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
    )


def update_execution_model(model: ToolExecutionModel, execution: ToolExecution) -> None:
    model.status = execution.status.value
    model.started_at = execution.started_at
    model.finished_at = execution.finished_at
    model.error_code = execution.error_code
    model.error_category = (
        execution.error_category.value if execution.error_category is not None else None
    )
