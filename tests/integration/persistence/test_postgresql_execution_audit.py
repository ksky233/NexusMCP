"""PostgreSQL ToolExecution 与 Append-Only Audit 短事务测试。"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from nexusmcp.infrastructure.identifiers import UuidIdentifierGenerator
from nexusmcp.modules.audit.domain import AuditOutcome
from nexusmcp.modules.catalog.domain import ToolSideEffect
from nexusmcp.modules.execution.adapters.sqlalchemy_uow import (
    SqlAlchemyExecutionUnitOfWorkFactory,
)
from nexusmcp.modules.execution.domain import ExecutionErrorCategory, ExecutionStatus
from nexusmcp.modules.execution.lifecycle import ExecutionLifecycle, PlanExecutionCommand
from nexusmcp.shared.request_context import ActorContext
from tests.contract.repositories.contracts import BINDING_ID, TENANT_A_ID, TOOL_ID, VERSION_ID
from tests.integration.persistence.test_mcp_read_only_http_call import seed_executable_tool

pytestmark = pytest.mark.integration


class FixedClock:
    def __init__(self) -> None:
        self._current = datetime(2026, 8, 26, 23, 0, tzinfo=UTC)

    def now(self) -> datetime:
        current = self._current
        self._current += timedelta(seconds=1)
        return current


def context(request_id: str) -> ActorContext:
    return ActorContext(
        request_id=request_id,
        trace_id="a" * 32,
        tenant_id=TENANT_A_ID,
        principal_id="user-a",
        authn_method="test",
    )


def plan_command(request_id: str) -> PlanExecutionCommand:
    return PlanExecutionCommand(
        context=context(request_id),
        principal_id="user-a",
        tool_id=TOOL_ID,
        tool_version_id=VERSION_ID,
        tool_binding_id=BINDING_ID,
        arguments_digest="1" * 64,
        policy_version="policy-v1",
        policy_reason_code="employee_reader_allowed",
        side_effect=ToolSideEffect.READ_ONLY,
    )


@pytest.mark.asyncio
async def test_execution_terminal_state_and_audit_are_persisted_together(
    pg_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with pg_session_factory() as seed_session:
        await seed_executable_tool(seed_session)
    factory = SqlAlchemyExecutionUnitOfWorkFactory(pg_session_factory)
    lifecycle = ExecutionLifecycle(factory, FixedClock(), UuidIdentifierGenerator())

    successful = await lifecycle.plan(plan_command("request-success"))
    await lifecycle.succeed(TENANT_A_ID, successful.id)
    unknown = await lifecycle.plan(plan_command("request-unknown"))
    await lifecycle.fail(
        TENANT_A_ID,
        unknown.id,
        error_code="response_lost_after_send",
        category=ExecutionErrorCategory.TIMEOUT_AFTER_SEND,
        outcome_unknown=True,
    )

    async with factory() as unit_of_work:
        executions = await unit_of_work.executions.list_by_tenant(TENANT_A_ID)
        successful_audits = await unit_of_work.audits.list_by_execution(
            TENANT_A_ID,
            successful.id,
        )
        unknown_audits = await unit_of_work.audits.list_by_execution(
            TENANT_A_ID,
            unknown.id,
        )

    assert [execution.status for execution in executions] == [
        ExecutionStatus.SUCCEEDED,
        ExecutionStatus.UNKNOWN,
    ]
    assert [event.outcome for event in successful_audits] == [
        AuditOutcome.ALLOWED,
        AuditOutcome.SUCCEEDED,
    ]
    assert [event.outcome for event in unknown_audits] == [
        AuditOutcome.ALLOWED,
        AuditOutcome.UNKNOWN,
    ]
    assert unknown_audits[-1].reason_code == "response_lost_after_send"
    assert all(event.metadata is not None for event in (*successful_audits, *unknown_audits))
    serialized = repr((*executions, *successful_audits, *unknown_audits))
    assert "arguments=" not in serialized
    assert "secret" not in serialized.lower()
