"""PostgreSQL Approval Repository、行锁与原子单次消费测试。"""

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from nexusmcp.infrastructure.identifiers import UuidIdentifierGenerator
from nexusmcp.modules.approval.adapters.sqlalchemy_uow import (
    SqlAlchemyApprovalUnitOfWorkFactory,
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
from nexusmcp.shared.errors import ApprovalAlreadyConsumedError
from nexusmcp.shared.request_context import ActorContext
from tests.contract.repositories.contracts import TENANT_A_ID, TOOL_ID, VERSION_ID
from tests.integration.persistence.test_mcp_read_only_http_call import seed_executable_tool

pytestmark = pytest.mark.integration

APPROVAL_ID = "00000000-0000-0000-0000-000000000090"
NOW = datetime(2026, 8, 26, 21, 0, tzinfo=UTC)


@dataclass(frozen=True, slots=True)
class FixedClock:
    def now(self) -> datetime:
        return NOW


class FixedIdentifierGenerator:
    def new_id(self) -> str:
        return APPROVAL_ID


def context(principal_id: str) -> ActorContext:
    return ActorContext(
        request_id="request-postgresql-approval",
        trace_id="a" * 32,
        tenant_id=TENANT_A_ID,
        principal_id=principal_id,
        authn_method="test",
    )


def consume_command() -> ConsumeApprovalCommand:
    return ConsumeApprovalCommand(
        context=context("agent-service-a"),
        approval_id=APPROVAL_ID,
        principal_id="agent-service-a",
        tool_version_id=VERSION_ID,
        arguments_digest="1" * 64,
        policy_version="policy-v1",
    )


@pytest.mark.asyncio
async def test_postgresql_row_lock_allows_exactly_one_approval_consumer(
    pg_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with pg_session_factory() as seed_session:
        await seed_executable_tool(seed_session)
    factory = SqlAlchemyApprovalUnitOfWorkFactory(pg_session_factory)
    clock = FixedClock()
    await RequestApproval(factory, clock, FixedIdentifierGenerator()).execute(
        RequestApprovalCommand(
            context=context("agent-service-a"),
            principal_id="agent-service-a",
            tool_id=TOOL_ID,
            tool_version_id=VERSION_ID,
            arguments_digest="1" * 64,
            policy_version="policy-v1",
        )
    )
    await DecideApproval(factory, clock, UuidIdentifierGenerator()).execute(
        DecideApprovalCommand(
            context=context("admin-a"),
            approval_id=APPROVAL_ID,
            approved=True,
        )
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
    persisted = await GetApproval(factory).execute(
        GetApprovalQuery(context=context("agent-service-a"), approval_id=APPROVAL_ID)
    )
    assert persisted.status is ApprovalStatus.CONSUMED
