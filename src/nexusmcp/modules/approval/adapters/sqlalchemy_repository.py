"""ApprovalRepository 的 SQLAlchemy Async Adapter。"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nexusmcp.infrastructure.persistence.identifiers import as_uuid
from nexusmcp.modules.approval.adapters.sqlalchemy_mapping import (
    approval_from_model,
    approval_to_model,
    update_approval_model,
)
from nexusmcp.modules.approval.adapters.sqlalchemy_models import ApprovalRequestModel
from nexusmcp.modules.approval.domain import ApprovalRequest
from nexusmcp.shared.errors import TenantBoundaryViolationError


class SqlAlchemyApprovalRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, tenant_id: str, approval: ApprovalRequest) -> None:
        _require_tenant(tenant_id, approval)
        self._session.add(approval_to_model(approval))
        await self._session.flush()

    async def get_for_update(
        self,
        tenant_id: str,
        approval_id: str,
    ) -> ApprovalRequest | None:
        model = await self._session.scalar(
            self._statement(tenant_id, approval_id).with_for_update()
        )
        return approval_from_model(model) if model is not None else None

    async def get_by_id(
        self,
        tenant_id: str,
        approval_id: str,
    ) -> ApprovalRequest | None:
        model = await self._session.scalar(self._statement(tenant_id, approval_id))
        return approval_from_model(model) if model is not None else None

    async def save(self, tenant_id: str, approval: ApprovalRequest) -> None:
        _require_tenant(tenant_id, approval)
        model = await self._session.scalar(self._statement(tenant_id, approval.id))
        if model is None:
            raise ValueError("approval does not exist in tenant")
        update_approval_model(model, approval)
        await self._session.flush()

    @staticmethod
    def _statement(tenant_id: str, approval_id: str):
        return select(ApprovalRequestModel).where(
            ApprovalRequestModel.tenant_id == as_uuid(tenant_id, field_name="tenant id"),
            ApprovalRequestModel.id == as_uuid(approval_id, field_name="approval id"),
        )


def _require_tenant(tenant_id: str, approval: ApprovalRequest) -> None:
    if approval.tenant_id != tenant_id:
        raise TenantBoundaryViolationError("approval crossed tenant boundary")
