"""Approval Domain 与 ORM Model 的显式映射。"""

from nexusmcp.infrastructure.persistence.identifiers import as_uuid
from nexusmcp.modules.approval.adapters.sqlalchemy_models import ApprovalRequestModel
from nexusmcp.modules.approval.domain import ApprovalRequest, ApprovalStatus


def approval_to_model(approval: ApprovalRequest) -> ApprovalRequestModel:
    return ApprovalRequestModel(
        id=as_uuid(approval.id, field_name="approval id"),
        tenant_id=as_uuid(approval.tenant_id, field_name="tenant id"),
        principal_id=approval.principal_id,
        tool_id=as_uuid(approval.tool_id, field_name="tool id"),
        tool_version_id=as_uuid(approval.tool_version_id, field_name="tool version id"),
        arguments_digest=approval.arguments_digest,
        policy_version=approval.policy_version,
        idempotency_key=approval.idempotency_key,
        status=approval.status.value,
        requested_at=approval.requested_at,
        expires_at=approval.expires_at,
        decided_by=approval.decided_by,
        decided_at=approval.decided_at,
        consumed_at=approval.consumed_at,
    )


def approval_from_model(model: ApprovalRequestModel) -> ApprovalRequest:
    return ApprovalRequest(
        id=str(model.id),
        tenant_id=str(model.tenant_id),
        principal_id=model.principal_id,
        tool_id=str(model.tool_id),
        tool_version_id=str(model.tool_version_id),
        arguments_digest=model.arguments_digest,
        policy_version=model.policy_version,
        idempotency_key=model.idempotency_key,
        status=ApprovalStatus(model.status),
        requested_at=model.requested_at,
        expires_at=model.expires_at,
        decided_by=model.decided_by,
        decided_at=model.decided_at,
        consumed_at=model.consumed_at,
    )


def update_approval_model(
    model: ApprovalRequestModel,
    approval: ApprovalRequest,
) -> None:
    model.status = approval.status.value
    model.decided_by = approval.decided_by
    model.decided_at = approval.decided_at
    model.consumed_at = approval.consumed_at
