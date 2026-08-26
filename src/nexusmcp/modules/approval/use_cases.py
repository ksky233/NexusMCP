"""Approval 创建、决策、查询与单次消费 Application Use Case。"""

from dataclasses import dataclass
from datetime import datetime, timedelta

from nexusmcp.modules.approval.domain import ApprovalRequest, ApprovalStatus
from nexusmcp.modules.approval.ports import ApprovalRepository, ApprovalUnitOfWorkFactory
from nexusmcp.modules.audit.domain import AuditAction, AuditEvent, AuditOutcome
from nexusmcp.shared.clock import Clock
from nexusmcp.shared.errors import (
    ApprovalAlreadyConsumedError,
    ApprovalExpiredError,
    ApprovalInvalidStateError,
    ApprovalMismatchError,
    ApprovalNotFoundError,
    ApprovalPendingError,
    ApprovalRejectedError,
)
from nexusmcp.shared.identifiers import IdentifierGenerator
from nexusmcp.shared.request_context import ActorContext


@dataclass(frozen=True, slots=True)
class RequestApprovalCommand:
    context: ActorContext
    principal_id: str
    tool_id: str
    tool_version_id: str
    arguments_digest: str
    policy_version: str
    policy_reason_code: str = "approval_required"


@dataclass(frozen=True, slots=True)
class ConsumeApprovalCommand:
    context: ActorContext
    approval_id: str
    principal_id: str
    tool_version_id: str
    arguments_digest: str
    policy_version: str


@dataclass(frozen=True, slots=True)
class DecideApprovalCommand:
    context: ActorContext
    approval_id: str
    approved: bool


@dataclass(frozen=True, slots=True)
class GetApprovalQuery:
    context: ActorContext
    approval_id: str


class RequestApproval:
    def __init__(
        self,
        unit_of_work_factory: ApprovalUnitOfWorkFactory,
        clock: Clock,
        identifier_generator: IdentifierGenerator,
        *,
        ttl_seconds: float = 600.0,
    ) -> None:
        if ttl_seconds <= 0:
            raise ValueError("approval ttl must be positive")
        self._unit_of_work_factory = unit_of_work_factory
        self._clock = clock
        self._identifier_generator = identifier_generator
        self._ttl_seconds = ttl_seconds

    async def execute(self, command: RequestApprovalCommand) -> ApprovalRequest:
        now = self._clock.now()
        approval = ApprovalRequest(
            id=self._identifier_generator.new_id(),
            tenant_id=command.context.tenant_id,
            principal_id=command.principal_id,
            tool_id=command.tool_id,
            tool_version_id=command.tool_version_id,
            arguments_digest=command.arguments_digest,
            policy_version=command.policy_version,
            status=ApprovalStatus.PENDING,
            requested_at=now,
            expires_at=now + timedelta(seconds=self._ttl_seconds),
        )
        async with self._unit_of_work_factory() as unit_of_work:
            await unit_of_work.approvals.add(command.context.tenant_id, approval)
            await unit_of_work.audits.append(
                AuditEvent(
                    id=self._identifier_generator.new_id(),
                    tenant_id=command.context.tenant_id,
                    actor_id=command.principal_id,
                    action=AuditAction.TOOL_CALL,
                    resource_type="tool_version",
                    resource_id=command.tool_version_id,
                    outcome=AuditOutcome.APPROVAL_REQUIRED,
                    request_id=command.context.request_id,
                    trace_id=command.context.trace_id,
                    occurred_at=now,
                    arguments_digest=command.arguments_digest,
                    policy_version=command.policy_version,
                    reason_code=command.policy_reason_code,
                )
            )
            await unit_of_work.commit()
        return approval


class DecideApproval:
    def __init__(
        self,
        unit_of_work_factory: ApprovalUnitOfWorkFactory,
        clock: Clock,
        identifier_generator: IdentifierGenerator,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._clock = clock
        self._identifier_generator = identifier_generator

    async def execute(self, command: DecideApprovalCommand) -> ApprovalRequest:
        tenant_id = command.context.tenant_id
        async with self._unit_of_work_factory() as unit_of_work:
            approval = await unit_of_work.approvals.get_for_update(
                tenant_id,
                command.approval_id,
            )
            if approval is None:
                raise ApprovalNotFoundError("approval did not exist in tenant")
            _require_pending_decision(approval)
            now = self._clock.now()
            if now >= approval.expires_at:
                expired = approval.expire(now)
                await unit_of_work.approvals.save(tenant_id, expired)
                await unit_of_work.commit()
                raise ApprovalExpiredError("approval expired before decision")
            if command.approved:
                decided = approval.approve(command.context.principal_id, now)
            else:
                decided = approval.reject(command.context.principal_id, now)
            await unit_of_work.approvals.save(tenant_id, decided)
            await unit_of_work.audits.append(
                AuditEvent(
                    id=self._identifier_generator.new_id(),
                    tenant_id=tenant_id,
                    actor_id=command.context.principal_id,
                    action=AuditAction.APPROVAL_DECISION,
                    resource_type="approval",
                    resource_id=approval.id,
                    outcome=AuditOutcome.ALLOWED if command.approved else AuditOutcome.DENIED,
                    request_id=command.context.request_id,
                    trace_id=command.context.trace_id,
                    occurred_at=now,
                    arguments_digest=approval.arguments_digest,
                    policy_version=approval.policy_version,
                    reason_code=("approval_approved" if command.approved else "approval_rejected"),
                )
            )
            await unit_of_work.commit()
        return decided


class ConsumeApproval:
    def __init__(self, unit_of_work_factory: ApprovalUnitOfWorkFactory, clock: Clock) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._clock = clock

    async def execute(self, command: ConsumeApprovalCommand) -> ApprovalRequest:
        async with self._unit_of_work_factory() as unit_of_work:
            try:
                consumed = await consume_locked_approval(
                    unit_of_work.approvals,
                    command,
                    self._clock.now(),
                )
            except ApprovalExpiredError:
                await unit_of_work.commit()
                raise
            await unit_of_work.commit()
        return consumed


class GetApproval:
    def __init__(self, unit_of_work_factory: ApprovalUnitOfWorkFactory) -> None:
        self._unit_of_work_factory = unit_of_work_factory

    async def execute(self, query: GetApprovalQuery) -> ApprovalRequest:
        async with self._unit_of_work_factory() as unit_of_work:
            approval = await unit_of_work.approvals.get_by_id(
                query.context.tenant_id,
                query.approval_id,
            )
        if approval is None:
            raise ApprovalNotFoundError("approval did not exist in tenant")
        return approval


def _require_pending_decision(approval: ApprovalRequest) -> None:
    if approval.status is ApprovalStatus.PENDING:
        return
    if approval.status is ApprovalStatus.EXPIRED:
        raise ApprovalExpiredError("expired approval cannot be decided")
    raise ApprovalInvalidStateError(f"{approval.status.value} approval cannot be decided")


def _require_consumable_status(approval: ApprovalRequest) -> None:
    if approval.status is ApprovalStatus.APPROVED:
        return
    if approval.status is ApprovalStatus.PENDING:
        raise ApprovalPendingError("approval was not decided")
    if approval.status is ApprovalStatus.REJECTED:
        raise ApprovalRejectedError("approval was rejected")
    if approval.status is ApprovalStatus.EXPIRED:
        raise ApprovalExpiredError("approval was expired")
    raise ApprovalAlreadyConsumedError("approval was already consumed")


def _require_matching_call(
    approval: ApprovalRequest,
    command: ConsumeApprovalCommand,
) -> None:
    if approval.principal_id != command.principal_id:
        raise ApprovalMismatchError("approval principal did not match")
    if approval.tool_version_id != command.tool_version_id:
        raise ApprovalMismatchError("approval tool version did not match")
    if approval.arguments_digest != command.arguments_digest:
        raise ApprovalMismatchError("approval arguments digest did not match")
    if approval.policy_version != command.policy_version:
        raise ApprovalMismatchError("approval policy version did not match")


async def consume_locked_approval(
    approvals: ApprovalRepository,
    command: ConsumeApprovalCommand,
    consumed_at: datetime,
) -> ApprovalRequest:
    """在调用方事务内锁定并消费 Approval；本函数不负责 Commit。"""

    tenant_id = command.context.tenant_id
    approval = await approvals.get_for_update(tenant_id, command.approval_id)
    if approval is None:
        raise ApprovalNotFoundError("approval did not exist in tenant")
    _require_consumable_status(approval)
    if consumed_at >= approval.expires_at:
        expired = approval.expire(consumed_at)
        await approvals.save(tenant_id, expired)
        raise ApprovalExpiredError("approval expired before consumption")
    _require_matching_call(approval, command)
    consumed = approval.consume(
        principal_id=command.principal_id,
        tool_version_id=command.tool_version_id,
        arguments_digest=command.arguments_digest,
        policy_version=command.policy_version,
        consumed_at=consumed_at,
    )
    await approvals.save(tenant_id, consumed)
    return consumed
