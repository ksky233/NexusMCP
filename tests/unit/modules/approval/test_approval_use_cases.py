"""Approval Application Use Case 与事务型单次消费测试。"""

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest

from nexusmcp.modules.approval.adapters.in_memory import (
    InMemoryApprovalUnitOfWorkFactory,
)
from nexusmcp.modules.approval.domain import ApprovalStatus
from nexusmcp.modules.approval.use_cases import (
    ConsumeApproval,
    ConsumeApprovalCommand,
    DecideApproval,
    DecideApprovalCommand,
    GetApproval,
    GetApprovalQuery,
    RequestApproval,
    RequestApprovalCommand,
)
from nexusmcp.shared.errors import (
    ApprovalAlreadyConsumedError,
    ApprovalExpiredError,
    ApprovalMismatchError,
    ApprovalRejectedError,
)
from nexusmcp.shared.request_context import ActorContext

NOW = datetime(2026, 8, 26, 20, 0, tzinfo=UTC)


@dataclass(slots=True)
class MutableClock:
    current: datetime = NOW

    def now(self) -> datetime:
        return self.current


class FixedIdentifierGenerator:
    def __init__(self) -> None:
        self._count = 0

    def new_id(self) -> str:
        self._count += 1
        return "approval-1" if self._count == 1 else f"request-audit-{self._count - 1}"


class DecisionAuditIdentifierGenerator:
    def new_id(self) -> str:
        return "decision-audit-1"


def context(principal_id: str = "user-a") -> ActorContext:
    return ActorContext(
        request_id="request-approval",
        trace_id="a" * 32,
        tenant_id="tenant-a",
        principal_id=principal_id,
        authn_method="test",
    )


def request_command() -> RequestApprovalCommand:
    return RequestApprovalCommand(
        context=context(),
        principal_id="user-a",
        tool_id="tool-1",
        tool_version_id="version-1",
        arguments_digest="1" * 64,
        policy_version="policy-v1",
    )


def consume_command(**changes: str) -> ConsumeApprovalCommand:
    values = {
        "approval_id": "approval-1",
        "principal_id": "user-a",
        "tool_version_id": "version-1",
        "arguments_digest": "1" * 64,
        "policy_version": "policy-v1",
    }
    values.update(changes)
    return ConsumeApprovalCommand(context=context(), **values)


@pytest.mark.asyncio
async def test_approved_request_is_consumed_and_remains_queryable() -> None:
    factory = InMemoryApprovalUnitOfWorkFactory()
    clock = MutableClock()
    requester = RequestApproval(factory, clock, FixedIdentifierGenerator())
    decider = DecideApproval(factory, clock, DecisionAuditIdentifierGenerator())
    consumer = ConsumeApproval(factory, clock)
    reader = GetApproval(factory)

    pending = await requester.execute(request_command())
    clock.current += timedelta(minutes=1)
    approved = await decider.execute(
        DecideApprovalCommand(
            context=context("admin-a"),
            approval_id=pending.id,
            approved=True,
        )
    )
    clock.current += timedelta(minutes=1)
    consumed = await consumer.execute(consume_command())

    persisted = await reader.execute(GetApprovalQuery(context=context(), approval_id=pending.id))
    assert approved.status is ApprovalStatus.APPROVED
    assert approved.decided_by == "admin-a"
    assert consumed.status is ApprovalStatus.CONSUMED
    assert persisted == consumed


@pytest.mark.asyncio
async def test_changed_call_snapshot_does_not_consume_approval() -> None:
    factory = InMemoryApprovalUnitOfWorkFactory()
    clock = MutableClock()
    requester = RequestApproval(factory, clock, FixedIdentifierGenerator())
    decider = DecideApproval(factory, clock, DecisionAuditIdentifierGenerator())
    consumer = ConsumeApproval(factory, clock)
    reader = GetApproval(factory)
    await requester.execute(request_command())
    await decider.execute(
        DecideApprovalCommand(context=context("admin-a"), approval_id="approval-1", approved=True)
    )

    with pytest.raises(ApprovalMismatchError):
        await consumer.execute(consume_command(arguments_digest="2" * 64))

    approval = await reader.execute(GetApprovalQuery(context=context(), approval_id="approval-1"))
    assert approval.status is ApprovalStatus.APPROVED


@pytest.mark.asyncio
async def test_rejected_and_expired_approvals_cannot_be_consumed() -> None:
    rejected_factory = InMemoryApprovalUnitOfWorkFactory()
    clock = MutableClock()
    await RequestApproval(
        rejected_factory,
        clock,
        FixedIdentifierGenerator(),
    ).execute(request_command())
    await DecideApproval(rejected_factory, clock, DecisionAuditIdentifierGenerator()).execute(
        DecideApprovalCommand(context=context("admin-a"), approval_id="approval-1", approved=False)
    )
    with pytest.raises(ApprovalRejectedError):
        await ConsumeApproval(rejected_factory, clock).execute(consume_command())

    expired_factory = InMemoryApprovalUnitOfWorkFactory()
    await RequestApproval(
        expired_factory,
        clock,
        FixedIdentifierGenerator(),
        ttl_seconds=10,
    ).execute(request_command())
    clock.current += timedelta(seconds=10)
    with pytest.raises(ApprovalExpiredError):
        await DecideApproval(
            expired_factory,
            clock,
            DecisionAuditIdentifierGenerator(),
        ).execute(
            DecideApprovalCommand(
                context=context("admin-a"),
                approval_id="approval-1",
                approved=True,
            )
        )


@pytest.mark.asyncio
async def test_two_concurrent_consumers_have_exactly_one_winner() -> None:
    factory = InMemoryApprovalUnitOfWorkFactory()
    clock = MutableClock()
    await RequestApproval(factory, clock, FixedIdentifierGenerator()).execute(request_command())
    await DecideApproval(factory, clock, DecisionAuditIdentifierGenerator()).execute(
        DecideApprovalCommand(context=context("admin-a"), approval_id="approval-1", approved=True)
    )
    consumer = ConsumeApproval(factory, clock)

    results = await asyncio.gather(
        consumer.execute(consume_command()),
        consumer.execute(consume_command()),
        return_exceptions=True,
    )

    assert (
        sum(
            result.status is ApprovalStatus.CONSUMED
            for result in results
            if not isinstance(result, BaseException)
        )
        == 1
    )
    assert sum(isinstance(result, ApprovalAlreadyConsumedError) for result in results) == 1
