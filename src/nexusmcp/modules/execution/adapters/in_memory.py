"""S3-1 使用的 InMemory ToolExecution Repository。"""

from nexusmcp.modules.execution.domain import ToolExecution


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

    async def list_by_tenant(self, tenant_id: str) -> tuple[ToolExecution, ...]:
        return tuple(
            execution for execution in self._executions.values() if execution.tenant_id == tenant_id
        )


def _require_tenant(requested_tenant_id: str, entity_tenant_id: str) -> None:
    if requested_tenant_id != entity_tenant_id:
        raise ValueError("entity tenant does not match repository tenant scope")
