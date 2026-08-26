"""Tool Resolution、Executor 与 Execution Persistence Port。"""

from collections.abc import Mapping
from typing import Any, Protocol

from nexusmcp.modules.credentials.domain import ResolvedCredential
from nexusmcp.modules.execution.domain import (
    ExecutorRequest,
    ExecutorResult,
    ResolvedExecutableTool,
    ToolExecution,
)


class ExecutableToolResolver(Protocol):
    async def resolve(
        self,
        tenant_id: str,
        canonical_name: str,
    ) -> ResolvedExecutableTool | None: ...


class ArgumentsValidator(Protocol):
    def validate(
        self,
        schema: Mapping[str, Any],
        arguments: Mapping[str, Any],
    ) -> None: ...


class ToolExecutor(Protocol):
    async def execute(
        self,
        request: ExecutorRequest,
        credential: ResolvedCredential | None,
    ) -> ExecutorResult: ...


class ToolExecutionRepository(Protocol):
    async def add(self, tenant_id: str, execution: ToolExecution) -> None: ...

    async def get_by_id(
        self,
        tenant_id: str,
        execution_id: str,
    ) -> ToolExecution | None: ...

    async def save(self, tenant_id: str, execution: ToolExecution) -> None: ...
