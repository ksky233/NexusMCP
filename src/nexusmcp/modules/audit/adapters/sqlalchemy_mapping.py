"""Audit Domain 与 ORM Model 的显式映射。"""

from nexusmcp.infrastructure.persistence.identifiers import as_uuid
from nexusmcp.modules.audit.adapters.sqlalchemy_models import AuditEventModel
from nexusmcp.modules.audit.domain import AuditAction, AuditEvent, AuditOutcome


def audit_to_model(event: AuditEvent) -> AuditEventModel:
    return AuditEventModel(
        id=as_uuid(event.id, field_name="audit id"),
        tenant_id=as_uuid(event.tenant_id, field_name="tenant id"),
        actor_id=event.actor_id,
        action=event.action.value,
        resource_type=event.resource_type,
        resource_id=event.resource_id,
        outcome=event.outcome.value,
        request_id=event.request_id,
        trace_id=event.trace_id,
        occurred_at=event.occurred_at,
        arguments_digest=event.arguments_digest,
        policy_version=event.policy_version,
        reason_code=event.reason_code,
        execution_id=(
            as_uuid(event.execution_id, field_name="execution id")
            if event.execution_id is not None
            else None
        ),
        metadata_json=dict(event.metadata or {}),
    )


def audit_from_model(model: AuditEventModel) -> AuditEvent:
    return AuditEvent(
        id=str(model.id),
        tenant_id=str(model.tenant_id),
        actor_id=model.actor_id,
        action=AuditAction(model.action),
        resource_type=model.resource_type,
        resource_id=model.resource_id,
        outcome=AuditOutcome(model.outcome),
        request_id=model.request_id,
        trace_id=model.trace_id,
        occurred_at=model.occurred_at,
        arguments_digest=model.arguments_digest,
        policy_version=model.policy_version,
        reason_code=model.reason_code,
        execution_id=str(model.execution_id) if model.execution_id is not None else None,
        metadata=dict(model.metadata_json),
    )
