"""S3-1 使用的 InMemory ToolExecution Repository。"""

from nexusmcp.modules.execution.domain import ExecutionAttempt, ToolExecution


class InMemoryToolExecutionRepository:
    def __init__(self, executions: dict[str, ToolExecution] | None = None) -> None:
        self._executions = executions if executions is not None else {}

    async def add(self, tenant_id: str, execution: ToolExecution) -> None:
        _require_tenant(tenant_id, execution.tenant_id)
        if execution.id in self._executions:
            raise ValueError("tool execution id already exists")
        self._executions[execution.id] = execution

    async def get_by_id(
        self,
        tenant_id: str,
        execution_id: str,
    ) -> ToolExecution | None:
        execution = self._executions.get(execution_id)
        return execution if execution is not None and execution.tenant_id == tenant_id else None

    async def get_for_update(
        self,
        tenant_id: str,
        execution_id: str,
    ) -> ToolExecution | None:
        return await self.get_by_id(tenant_id, execution_id)

    async def save(self, tenant_id: str, execution: ToolExecution) -> None:
        _require_tenant(tenant_id, execution.tenant_id)
        current = self._executions.get(execution.id)
        if current is None or current.tenant_id != tenant_id:
            raise ValueError("tool execution does not exist in tenant")
        self._executions[execution.id] = execution

    async def get_by_idempotency_key(
        self,
        tenant_id: str,
        principal_id: str,
        tool_version_id: str,
        idempotency_key: str,
    ) -> ToolExecution | None:
        return next(
            (
                execution
                for execution in self._executions.values()
                if execution.tenant_id == tenant_id
                and execution.principal_id == principal_id
                and execution.tool_version_id == tool_version_id
                and execution.idempotency_key == idempotency_key
            ),
            None,
        )

    async def list_by_tenant(self, tenant_id: str) -> tuple[ToolExecution, ...]:
        return tuple(
            execution for execution in self._executions.values() if execution.tenant_id == tenant_id
        )


def _require_tenant(requested_tenant_id: str, entity_tenant_id: str) -> None:
    if requested_tenant_id != entity_tenant_id:
        raise ValueError("entity tenant does not match repository tenant scope")


class InMemoryExecutionAttemptRepository:
    def __init__(self, attempts: dict[str, ExecutionAttempt] | None = None) -> None:
        self._attempts = attempts if attempts is not None else {}

    async def add(self, tenant_id: str, attempt: ExecutionAttempt) -> None:
        _require_tenant(tenant_id, attempt.tenant_id)
        if attempt.id in self._attempts:
            raise ValueError("execution attempt id already exists")
        if any(
            current.execution_id == attempt.execution_id
            and current.attempt_number == attempt.attempt_number
            for current in self._attempts.values()
        ):
            raise ValueError("execution attempt number already exists")
        self._attempts[attempt.id] = attempt

    async def get_for_update(
        self,
        tenant_id: str,
        attempt_id: str,
    ) -> ExecutionAttempt | None:
        attempt = self._attempts.get(attempt_id)
        return attempt if attempt is not None and attempt.tenant_id == tenant_id else None

    async def save(self, tenant_id: str, attempt: ExecutionAttempt) -> None:
        _require_tenant(tenant_id, attempt.tenant_id)
        current = self._attempts.get(attempt.id)
        if current is None or current.tenant_id != tenant_id:
            raise ValueError("execution attempt does not exist in tenant")
        self._attempts[attempt.id] = attempt

    async def list_by_execution(
        self,
        tenant_id: str,
        execution_id: str,
    ) -> tuple[ExecutionAttempt, ...]:
        return tuple(
            sorted(
                (
                    attempt
                    for attempt in self._attempts.values()
                    if attempt.tenant_id == tenant_id and attempt.execution_id == execution_id
                ),
                key=lambda attempt: attempt.attempt_number,
            )
        )
