"""ToolExecutionRepository 的 SQLAlchemy Async Adapter。"""

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from nexusmcp.infrastructure.persistence.identifiers import as_uuid
from nexusmcp.modules.execution.adapters.sqlalchemy_mapping import (
    execution_from_model,
    execution_to_model,
    update_execution_model,
)
from nexusmcp.modules.execution.adapters.sqlalchemy_models import ToolExecutionModel
from nexusmcp.modules.execution.domain import ToolExecution
from nexusmcp.shared.errors import TenantBoundaryViolationError


class SqlAlchemyToolExecutionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, tenant_id: str, execution: ToolExecution) -> None:
        _require_tenant(tenant_id, execution)
        self._session.add(execution_to_model(execution))
        await self._session.flush()

    async def get_by_id(
        self,
        tenant_id: str,
        execution_id: str,
    ) -> ToolExecution | None:
        model = await self._session.scalar(self._statement(tenant_id, execution_id))
        return execution_from_model(model) if model is not None else None

    async def get_for_update(
        self,
        tenant_id: str,
        execution_id: str,
    ) -> ToolExecution | None:
        model = await self._session.scalar(
            self._statement(tenant_id, execution_id).with_for_update()
        )
        return execution_from_model(model) if model is not None else None

    async def save(self, tenant_id: str, execution: ToolExecution) -> None:
        _require_tenant(tenant_id, execution)
        model = await self._session.scalar(self._statement(tenant_id, execution.id))
        if model is None:
            raise ValueError("tool execution does not exist in tenant")
        update_execution_model(model, execution)
        await self._session.flush()

    async def list_by_tenant(self, tenant_id: str) -> tuple[ToolExecution, ...]:
        models = (
            await self._session.scalars(
                select(ToolExecutionModel)
                .where(ToolExecutionModel.tenant_id == as_uuid(tenant_id, field_name="tenant id"))
                .order_by(ToolExecutionModel.planned_at, ToolExecutionModel.id)
            )
        ).all()
        return tuple(execution_from_model(model) for model in models)

    @staticmethod
    def _statement(
        tenant_id: str,
        execution_id: str,
    ) -> Select[tuple[ToolExecutionModel]]:
        return select(ToolExecutionModel).where(
            ToolExecutionModel.tenant_id == as_uuid(tenant_id, field_name="tenant id"),
            ToolExecutionModel.id == as_uuid(execution_id, field_name="execution id"),
        )


def _require_tenant(tenant_id: str, execution: ToolExecution) -> None:
    if execution.tenant_id != tenant_id:
        raise TenantBoundaryViolationError("tool execution crossed tenant boundary")
