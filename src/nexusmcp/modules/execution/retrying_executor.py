"""在一个 ToolExecution 内编排持久化 Attempt 与有界 Retry。"""

import asyncio

from nexusmcp.modules.catalog.domain import ToolSideEffect
from nexusmcp.modules.credentials.domain import ResolvedCredential
from nexusmcp.modules.execution.domain import (
    ExecutionErrorCategory,
    ExecutorFailure,
    ExecutorRequest,
    ExecutorResult,
    RetryDisposition,
    retry_disposition,
)
from nexusmcp.modules.execution.lifecycle import ExecutionLifecycle
from nexusmcp.modules.execution.ports import RetrySleeper, ToolExecutor


class ExecuteWithRetry:
    def __init__(
        self,
        executor: ToolExecutor,
        execution_lifecycle: ExecutionLifecycle,
        sleeper: RetrySleeper,
        *,
        max_attempts: int = 3,
        initial_backoff_seconds: float = 0.05,
    ) -> None:
        if max_attempts <= 0:
            raise ValueError("retry max attempts must be positive")
        if initial_backoff_seconds < 0:
            raise ValueError("retry backoff must not be negative")
        self._executor = executor
        self._execution_lifecycle = execution_lifecycle
        self._sleeper = sleeper
        self._max_attempts = max_attempts
        self._initial_backoff_seconds = initial_backoff_seconds

    async def execute(
        self,
        request: ExecutorRequest,
        credential: ResolvedCredential | None,
    ) -> ExecutorResult:
        tenant_id = request.tool.tenant_id
        for attempt_number in range(1, self._max_attempts + 1):
            attempt = await self._execution_lifecycle.start_attempt(
                tenant_id,
                request.execution_id,
            )
            try:
                result = await self._executor.execute(request, credential)
            except asyncio.CancelledError:
                await self._execution_lifecycle.cancel_attempt(tenant_id, attempt.id)
                raise
            except ExecutorFailure as error:
                await self._execution_lifecycle.fail_attempt(
                    tenant_id,
                    attempt.id,
                    error_code=error.code,
                    category=error.category,
                    outcome_unknown=error.outcome_unknown,
                    upstream_status=error.upstream_status,
                )
                disposition = retry_disposition(
                    side_effect=request.tool.side_effect,
                    error_category=error.category,
                    has_idempotency_key=request.idempotency_key is not None,
                )
                if disposition is RetryDisposition.RETRY and attempt_number < self._max_attempts:
                    await self._sleeper.sleep(
                        self._initial_backoff_seconds * (2 ** (attempt_number - 1))
                    )
                    continue
                if (
                    request.tool.side_effect is ToolSideEffect.READ_ONLY
                    and error.outcome_unknown
                    and disposition is not RetryDisposition.REQUIRE_RECONCILIATION
                ):
                    raise ExecutorFailure(
                        code=error.code,
                        category=error.category,
                        outcome_unknown=False,
                        upstream_status=error.upstream_status,
                    ) from None
                raise
            except Exception:
                await self._execution_lifecycle.fail_attempt(
                    tenant_id,
                    attempt.id,
                    error_code="unexpected_executor_failure",
                    category=ExecutionErrorCategory.UNKNOWN,
                    outcome_unknown=True,
                )
                raise
            else:
                await self._execution_lifecycle.succeed_attempt(
                    tenant_id,
                    attempt.id,
                    upstream_status=result.upstream_status,
                )
                return result

        raise RuntimeError("retry loop exhausted without a terminal result")  # pragma: no cover
