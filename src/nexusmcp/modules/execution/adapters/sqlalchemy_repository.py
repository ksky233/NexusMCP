"""ToolExecutionRepository 的 SQLAlchemy Async Adapter。"""

from sqlalchemy import Select, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from nexusmcp.infrastructure.persistence.identifiers import as_uuid
from nexusmcp.modules.execution.adapters.sqlalchemy_mapping import (
    attempt_from_model,
    attempt_to_model,
    execution_from_model,
    execution_to_model,
    update_attempt_model,
    update_execution_model,
)
from nexusmcp.modules.execution.adapters.sqlalchemy_models import (
    ExecutionAttemptModel,
    ToolExecutionModel,
)
from nexusmcp.modules.execution.domain import ExecutionAttempt, ToolExecution
from nexusmcp.shared.errors import IdempotencyRaceError, TenantBoundaryViolationError


class SqlAlchemyToolExecutionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, tenant_id: str, execution: ToolExecution) -> None:
        _require_tenant(tenant_id, execution)
        self._session.add(execution_to_model(execution))
        try:
            await self._session.flush()
        except IntegrityError as error:
            if "uq_tool_execution_idempotency_scope" in str(error):
                raise IdempotencyRaceError("concurrent idempotency claim lost") from None
            raise

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

    async def get_by_idempotency_key(
        self,
        tenant_id: str,
        principal_id: str,
        tool_version_id: str,
        idempotency_key: str,
    ) -> ToolExecution | None:
        model = await self._session.scalar(
            select(ToolExecutionModel).where(
                ToolExecutionModel.tenant_id == as_uuid(tenant_id, field_name="tenant id"),
                ToolExecutionModel.principal_id == principal_id,
                ToolExecutionModel.tool_version_id
                == as_uuid(tool_version_id, field_name="tool version id"),
                ToolExecutionModel.idempotency_key == idempotency_key,
            )
        )
        return execution_from_model(model) if model is not None else None

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


class SqlAlchemyExecutionAttemptRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, tenant_id: str, attempt: ExecutionAttempt) -> None:
        _require_attempt_tenant(tenant_id, attempt)
        self._session.add(attempt_to_model(attempt))
        await self._session.flush()

    async def get_for_update(
        self,
        tenant_id: str,
        attempt_id: str,
    ) -> ExecutionAttempt | None:
        model = await self._session.scalar(self._statement(tenant_id, attempt_id).with_for_update())
        return attempt_from_model(model) if model is not None else None

    async def save(self, tenant_id: str, attempt: ExecutionAttempt) -> None:
        _require_attempt_tenant(tenant_id, attempt)
        model = await self._session.scalar(self._statement(tenant_id, attempt.id))
        if model is None:
            raise ValueError("execution attempt does not exist in tenant")
        update_attempt_model(model, attempt)
        await self._session.flush()

    async def list_by_execution(
        self,
        tenant_id: str,
        execution_id: str,
    ) -> tuple[ExecutionAttempt, ...]:
        models = (
            await self._session.scalars(
                select(ExecutionAttemptModel)
                .where(
                    ExecutionAttemptModel.tenant_id == as_uuid(tenant_id, field_name="tenant id"),
                    ExecutionAttemptModel.execution_id
                    == as_uuid(execution_id, field_name="execution id"),
                )
                .order_by(ExecutionAttemptModel.attempt_number)
            )
        ).all()
        return tuple(attempt_from_model(model) for model in models)

    @staticmethod
    def _statement(
        tenant_id: str,
        attempt_id: str,
    ) -> Select[tuple[ExecutionAttemptModel]]:
        return select(ExecutionAttemptModel).where(
            ExecutionAttemptModel.tenant_id == as_uuid(tenant_id, field_name="tenant id"),
            ExecutionAttemptModel.id == as_uuid(attempt_id, field_name="execution attempt id"),
        )


def _require_attempt_tenant(tenant_id: str, attempt: ExecutionAttempt) -> None:
    if attempt.tenant_id != tenant_id:
        raise TenantBoundaryViolationError("execution attempt crossed tenant boundary")
