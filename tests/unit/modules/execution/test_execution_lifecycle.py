"""Execution/Approval/Audit 短事务与回滚测试。"""

from dataclasses import dataclass
from datetime import UTC, datetime
from types import TracebackType

import pytest

from nexusmcp.modules.approval.domain import ApprovalStatus
from nexusmcp.modules.approval.use_cases import (
    DecideApproval,
    DecideApprovalCommand,
    GetApproval,
    GetApprovalQuery,
    RequestApproval,
    RequestApprovalCommand,
)
from nexusmcp.modules.audit.adapters.in_memory import InMemoryAuditRepository
from nexusmcp.modules.audit.domain import AuditEvent, AuditOutcome
from nexusmcp.modules.catalog.domain import ToolSideEffect
from nexusmcp.modules.execution.adapters.in_memory_uow import (
    InMemoryExecutionUnitOfWork,
    InMemoryExecutionUnitOfWorkFactory,
)
from nexusmcp.modules.execution.domain import ExecutionStatus
from nexusmcp.modules.execution.lifecycle import ExecutionLifecycle, PlanExecutionCommand
from nexusmcp.shared.errors import (
    IdempotencyAlreadyCompletedError,
    IdempotencyConflictError,
    IdempotencyInProgressError,
)
from nexusmcp.shared.request_context import ActorContext

NOW = datetime(2026, 8, 26, 22, 0, tzinfo=UTC)


@dataclass(frozen=True, slots=True)
class FixedClock:
    def now(self) -> datetime:
        return NOW


class SequentialIdentifierGenerator:
    def __init__(self, prefix: str) -> None:
        self._prefix = prefix
        self._value = 0

    def new_id(self) -> str:
        self._value += 1
        return f"{self._prefix}-{self._value}"


def context(principal_id: str = "user-a") -> ActorContext:
    return ActorContext(
        request_id="request-lifecycle",
        trace_id="a" * 32,
        tenant_id="tenant-a",
        principal_id=principal_id,
        authn_method="test",
    )


def plan_command(
    *,
    approval_id: str | None = None,
    idempotency_key: str | None = None,
    arguments_digest: str = "1" * 64,
) -> PlanExecutionCommand:
    return PlanExecutionCommand(
        context=context(),
        principal_id="user-a",
        tool_id="tool-1",
        tool_version_id="version-1",
        tool_binding_id="binding-1",
        arguments_digest=arguments_digest,
        policy_version="policy-v1",
        policy_reason_code="allowed_after_approval",
        side_effect=ToolSideEffect.READ_ONLY,
        approval_id=approval_id,
        idempotency_key=idempotency_key,
    )


async def approved_request(factory: InMemoryExecutionUnitOfWorkFactory) -> str:
    approval = await RequestApproval(
        factory,
        FixedClock(),
        SequentialIdentifierGenerator("approval"),
    ).execute(
        RequestApprovalCommand(
            context=context(),
            principal_id="user-a",
            tool_id="tool-1",
            tool_version_id="version-1",
            arguments_digest="1" * 64,
            policy_version="policy-v1",
        )
    )
    await DecideApproval(
        factory,
        FixedClock(),
        SequentialIdentifierGenerator("decision"),
    ).execute(
        DecideApprovalCommand(
            context=context("admin-a"),
            approval_id=approval.id,
            approved=True,
        )
    )
    return approval.id


@pytest.mark.asyncio
async def test_plan_atomically_consumes_approval_and_records_allowed_audit() -> None:
    factory = InMemoryExecutionUnitOfWorkFactory()
    approval_id = await approved_request(factory)
    lifecycle = ExecutionLifecycle(
        factory,
        FixedClock(),
        SequentialIdentifierGenerator("record"),
    )
    running = await lifecycle.plan(plan_command(approval_id=approval_id))
    succeeded = await lifecycle.succeed("tenant-a", running.id)

    approval = await GetApproval(factory).execute(
        GetApprovalQuery(context=context(), approval_id=approval_id)
    )
    executions = await factory.execution_reader.list_by_tenant("tenant-a")
    audits = await factory.audit_reader.list_by_execution("tenant-a", running.id)
    assert approval.status is ApprovalStatus.CONSUMED
    assert succeeded.status is ExecutionStatus.SUCCEEDED
    assert executions == (succeeded,)
    assert [event.outcome for event in audits] == [
        AuditOutcome.ALLOWED,
        AuditOutcome.SUCCEEDED,
    ]
    assert all(event.arguments_digest == "1" * 64 for event in audits)
    assert all("arguments" not in (event.metadata or {}) for event in audits)


class FailingAuditRepository:
    def __init__(self, wrapped: InMemoryAuditRepository) -> None:
        self._wrapped = wrapped

    async def append(self, event: AuditEvent) -> None:
        _ = event
        raise RuntimeError("audit append failed")

    async def list_by_tenant(self, tenant_id: str) -> tuple[AuditEvent, ...]:
        return await self._wrapped.list_by_tenant(tenant_id)

    async def list_by_execution(
        self,
        tenant_id: str,
        execution_id: str,
    ) -> tuple[AuditEvent, ...]:
        return await self._wrapped.list_by_execution(tenant_id, execution_id)


class FailingAuditUnitOfWork:
    def __init__(self, wrapped: InMemoryExecutionUnitOfWork) -> None:
        self._wrapped = wrapped

    @property
    def executions(self):
        return self._wrapped.executions

    @property
    def approvals(self):
        return self._wrapped.approvals

    @property
    def attempts(self):
        return self._wrapped.attempts

    @property
    def audits(self) -> FailingAuditRepository:
        return FailingAuditRepository(self._wrapped.audits)

    async def __aenter__(self):
        await self._wrapped.__aenter__()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self._wrapped.__aexit__(exc_type, exc_value, traceback)

    async def commit(self) -> None:
        await self._wrapped.commit()

    async def rollback(self) -> None:
        await self._wrapped.rollback()


class FailingAuditUnitOfWorkFactory:
    def __init__(self, wrapped: InMemoryExecutionUnitOfWorkFactory) -> None:
        self._wrapped = wrapped

    def __call__(self) -> FailingAuditUnitOfWork:
        return FailingAuditUnitOfWork(self._wrapped())


@pytest.mark.asyncio
async def test_audit_failure_rolls_back_approval_consumption_and_execution_plan() -> None:
    factory = InMemoryExecutionUnitOfWorkFactory()
    approval_id = await approved_request(factory)
    lifecycle = ExecutionLifecycle(
        FailingAuditUnitOfWorkFactory(factory),
        FixedClock(),
        SequentialIdentifierGenerator("record"),
    )
    audits_before = await factory.audit_reader.list_by_tenant("tenant-a")

    with pytest.raises(RuntimeError, match="audit append failed"):
        await lifecycle.plan(plan_command(approval_id=approval_id))

    approval = await GetApproval(factory).execute(
        GetApprovalQuery(context=context(), approval_id=approval_id)
    )
    assert approval.status is ApprovalStatus.APPROVED
    assert await factory.execution_reader.list_by_tenant("tenant-a") == ()
    assert await factory.audit_reader.list_by_tenant("tenant-a") == audits_before


@pytest.mark.asyncio
async def test_idempotency_key_reuse_is_classified_by_digest_and_execution_status() -> None:
    factory = InMemoryExecutionUnitOfWorkFactory()
    lifecycle = ExecutionLifecycle(
        factory,
        FixedClock(),
        SequentialIdentifierGenerator("record"),
    )
    running = await lifecycle.plan(plan_command(idempotency_key="write-key-1"))

    with pytest.raises(IdempotencyInProgressError) as in_progress:
        await lifecycle.plan(plan_command(idempotency_key="write-key-1"))
    with pytest.raises(IdempotencyConflictError) as conflict:
        await lifecycle.plan(
            plan_command(
                idempotency_key="write-key-1",
                arguments_digest="2" * 64,
            )
        )

    await lifecycle.succeed("tenant-a", running.id)
    with pytest.raises(IdempotencyAlreadyCompletedError) as completed:
        await lifecycle.plan(plan_command(idempotency_key="write-key-1"))

    assert in_progress.value.execution_id == running.id
    assert conflict.value.execution_id == running.id
    assert completed.value.execution_id == running.id
    assert len(await factory.execution_reader.list_by_tenant("tenant-a")) == 1
