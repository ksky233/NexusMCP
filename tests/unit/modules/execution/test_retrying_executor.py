"""一个 Execution 内的 Attempt、Backoff 与 Retry Matrix 测试。"""

from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta

import pytest

from nexusmcp.modules.catalog.domain import ToolSideEffect
from nexusmcp.modules.credentials.domain import ResolvedCredential
from nexusmcp.modules.execution.adapters.in_memory_uow import (
    InMemoryExecutionUnitOfWorkFactory,
)
from nexusmcp.modules.execution.domain import (
    ExecutionAttemptStatus,
    ExecutionErrorCategory,
    ExecutionStatus,
    ExecutorFailure,
    ExecutorRequest,
    ExecutorResult,
)
from nexusmcp.modules.execution.lifecycle import ExecutionLifecycle, PlanExecutionCommand
from nexusmcp.modules.execution.retrying_executor import ExecuteWithRetry
from nexusmcp.shared.request_context import ActorContext
from tests.unit.modules.execution.test_call_tool import executable_tool


@dataclass(slots=True)
class SteppingClock:
    current: datetime = datetime(2026, 8, 26, 23, 30, tzinfo=UTC)

    def now(self) -> datetime:
        current = self.current
        self.current += timedelta(milliseconds=1)
        return current


class SequentialIdentifierGenerator:
    def __init__(self) -> None:
        self._value = 0

    def new_id(self) -> str:
        self._value += 1
        return f"record-{self._value}"


class RecordingSleeper:
    def __init__(self) -> None:
        self.delays: list[float] = []

    async def sleep(self, seconds: float) -> None:
        self.delays.append(seconds)


class SequenceExecutor:
    def __init__(self, outcomes: list[ExecutorFailure | ExecutorResult]) -> None:
        self._outcomes = outcomes
        self.calls = 0

    async def execute(
        self,
        request: ExecutorRequest,
        credential: ResolvedCredential | None,
    ) -> ExecutorResult:
        _ = (request, credential)
        outcome = self._outcomes[self.calls]
        self.calls += 1
        if isinstance(outcome, ExecutorFailure):
            raise outcome
        return outcome


def context() -> ActorContext:
    return ActorContext(
        request_id="request-retry",
        trace_id="a" * 32,
        tenant_id="tenant-a",
        principal_id="agent-service-a",
        authn_method="test",
    )


def plan_command(side_effect: ToolSideEffect, idempotency_key: str | None) -> PlanExecutionCommand:
    return PlanExecutionCommand(
        context=context(),
        principal_id="agent-service-a",
        tool_id="tool-1",
        tool_version_id="version-1",
        tool_binding_id="binding-1",
        arguments_digest="1" * 64,
        policy_version="policy-v1",
        policy_reason_code="allowed",
        side_effect=side_effect,
        idempotency_key=idempotency_key,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("side_effect", "idempotency_key"),
    [
        (ToolSideEffect.READ_ONLY, None),
        (ToolSideEffect.IDEMPOTENT_WRITE, "write-key-1"),
    ],
)
async def test_retryable_failures_create_attempts_then_succeed(
    side_effect: ToolSideEffect,
    idempotency_key: str | None,
) -> None:
    factory = InMemoryExecutionUnitOfWorkFactory()
    lifecycle = ExecutionLifecycle(factory, SteppingClock(), SequentialIdentifierGenerator())
    execution = await lifecycle.plan(plan_command(side_effect, idempotency_key))
    executor = SequenceExecutor(
        [
            ExecutorFailure(
                code="upstream_503",
                category=ExecutionErrorCategory.UPSTREAM_5XX,
                upstream_status=503,
            ),
            ExecutorFailure(
                code="upstream_network_error",
                category=ExecutionErrorCategory.NETWORK,
            ),
            ExecutorResult(data={"ok": True}, content_type="application/json", upstream_status=200),
        ]
    )
    sleeper = RecordingSleeper()
    retrying = ExecuteWithRetry(
        executor,
        lifecycle,
        sleeper,
        max_attempts=3,
        initial_backoff_seconds=0.1,
    )
    tool = replace(executable_tool(), side_effect=side_effect)

    result = await retrying.execute(
        ExecutorRequest(
            execution_id=execution.id,
            tool=tool,
            arguments={"employee_id": "emp-001"},
            timeout_seconds=1,
            idempotency_key=idempotency_key,
        ),
        credential=None,
    )
    terminal = await lifecycle.succeed("tenant-a", execution.id)
    attempts = await factory.attempt_reader.list_by_execution("tenant-a", execution.id)

    assert result.upstream_status == 200
    assert executor.calls == 3
    assert sleeper.delays == [0.1, 0.2]
    assert [attempt.status for attempt in attempts] == [
        ExecutionAttemptStatus.FAILED,
        ExecutionAttemptStatus.FAILED,
        ExecutionAttemptStatus.SUCCEEDED,
    ]
    assert attempts[0].upstream_status == 503
    assert terminal.status is ExecutionStatus.SUCCEEDED
    assert terminal.attempt_count == 3


@pytest.mark.asyncio
async def test_non_idempotent_after_send_timeout_is_not_retried() -> None:
    factory = InMemoryExecutionUnitOfWorkFactory()
    lifecycle = ExecutionLifecycle(factory, SteppingClock(), SequentialIdentifierGenerator())
    execution = await lifecycle.plan(plan_command(ToolSideEffect.NON_IDEMPOTENT_WRITE, None))
    failure = ExecutorFailure(
        code="upstream_timeout",
        category=ExecutionErrorCategory.TIMEOUT_AFTER_SEND,
        outcome_unknown=True,
    )
    executor = SequenceExecutor([failure])
    sleeper = RecordingSleeper()
    retrying = ExecuteWithRetry(executor, lifecycle, sleeper, max_attempts=3)
    tool = replace(executable_tool(), side_effect=ToolSideEffect.NON_IDEMPOTENT_WRITE)

    with pytest.raises(ExecutorFailure) as captured:
        await retrying.execute(
            ExecutorRequest(
                execution_id=execution.id,
                tool=tool,
                arguments={"employee_id": "emp-001"},
                timeout_seconds=1,
            ),
            credential=None,
        )
    terminal = await lifecycle.fail(
        "tenant-a",
        execution.id,
        error_code=captured.value.code,
        category=captured.value.category,
        outcome_unknown=captured.value.outcome_unknown,
    )
    attempts = await factory.attempt_reader.list_by_execution("tenant-a", execution.id)

    assert executor.calls == 1
    assert sleeper.delays == []
    assert len(attempts) == 1 and attempts[0].status is ExecutionAttemptStatus.UNKNOWN
    assert terminal.status is ExecutionStatus.UNKNOWN
