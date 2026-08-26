"""Tool Resolution、Executor 与 Execution Persistence Port。"""

from collections.abc import Mapping
from types import TracebackType
from typing import Any, Protocol, Self

from nexusmcp.modules.approval.ports import ApprovalRepository
from nexusmcp.modules.audit.ports import AuditRepository
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

    async def get_for_update(
        self,
        tenant_id: str,
        execution_id: str,
    ) -> ToolExecution | None: ...

    async def save(self, tenant_id: str, execution: ToolExecution) -> None: ...

    async def list_by_tenant(self, tenant_id: str) -> tuple[ToolExecution, ...]: ...


class ExecutionUnitOfWork(Protocol):
    @property
    def executions(self) -> ToolExecutionRepository: ...

    @property
    def approvals(self) -> ApprovalRepository: ...

    @property
    def audits(self) -> AuditRepository: ...

    async def __aenter__(self) -> Self: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...


class ExecutionUnitOfWorkFactory(Protocol):
    def __call__(self) -> ExecutionUnitOfWork: ...
