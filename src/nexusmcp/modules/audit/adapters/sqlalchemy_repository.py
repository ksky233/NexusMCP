"""Append-Only AuditRepository 的 SQLAlchemy Async Adapter。"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nexusmcp.infrastructure.persistence.identifiers import as_uuid
from nexusmcp.modules.audit.adapters.sqlalchemy_mapping import (
    audit_from_model,
    audit_to_model,
)
from nexusmcp.modules.audit.adapters.sqlalchemy_models import AuditEventModel
from nexusmcp.modules.audit.domain import AuditEvent
from nexusmcp.shared.errors import TenantBoundaryViolationError


class SqlAlchemyAuditRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def append(self, event: AuditEvent) -> None:
        self._session.add(audit_to_model(event))
        await self._session.flush()

    async def list_by_tenant(self, tenant_id: str) -> tuple[AuditEvent, ...]:
        models = (
            await self._session.scalars(
                select(AuditEventModel)
                .where(AuditEventModel.tenant_id == as_uuid(tenant_id, field_name="tenant id"))
                .order_by(AuditEventModel.occurred_at, AuditEventModel.id)
            )
        ).all()
        return tuple(audit_from_model(model) for model in models)

    async def list_by_execution(
        self,
        tenant_id: str,
        execution_id: str,
    ) -> tuple[AuditEvent, ...]:
        tenant_uuid = as_uuid(tenant_id, field_name="tenant id")
        execution_uuid = as_uuid(execution_id, field_name="execution id")
        models = (
            await self._session.scalars(
                select(AuditEventModel)
                .where(
                    AuditEventModel.tenant_id == tenant_uuid,
                    AuditEventModel.execution_id == execution_uuid,
                )
                .order_by(AuditEventModel.occurred_at, AuditEventModel.id)
            )
        ).all()
        events = tuple(audit_from_model(model) for model in models)
        if any(event.tenant_id != tenant_id for event in events):  # pragma: no cover
            raise TenantBoundaryViolationError("audit event crossed tenant boundary")
        return events
