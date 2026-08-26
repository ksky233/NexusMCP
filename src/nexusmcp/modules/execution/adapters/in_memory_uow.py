"""Execution/Approval/Audit 原子测试使用的 InMemory UoW。"""

from __future__ import annotations

import asyncio
from types import TracebackType

from nexusmcp.modules.approval.adapters.in_memory import InMemoryApprovalRepository
from nexusmcp.modules.approval.domain import ApprovalRequest
from nexusmcp.modules.audit.adapters.in_memory import InMemoryAuditRepository
from nexusmcp.modules.audit.domain import AuditEvent
from nexusmcp.modules.execution.adapters.in_memory import (
    InMemoryExecutionAttemptRepository,
    InMemoryToolExecutionRepository,
)
from nexusmcp.modules.execution.domain import ExecutionAttempt, ToolExecution


class InMemoryExecutionUnitOfWork:
    def __init__(
        self,
        *,
        execution_store: dict[str, ToolExecution],
        attempt_store: dict[str, ExecutionAttempt],
        approval_store: dict[str, ApprovalRequest],
        audit_store: dict[str, AuditEvent],
        lock: asyncio.Lock,
    ) -> None:
        self._stores = (execution_store, attempt_store, approval_store, audit_store)
        self._lock = lock
        self._working: (
            tuple[
                dict[str, ToolExecution],
                dict[str, ExecutionAttempt],
                dict[str, ApprovalRequest],
                dict[str, AuditEvent],
            ]
            | None
        ) = None
        self._executions: InMemoryToolExecutionRepository | None = None
        self._attempts: InMemoryExecutionAttemptRepository | None = None
        self._approvals: InMemoryApprovalRepository | None = None
        self._audits: InMemoryAuditRepository | None = None

    @property
    def executions(self) -> InMemoryToolExecutionRepository:
        if self._executions is None:
            raise RuntimeError("unit of work must be entered before accessing repositories")
        return self._executions

    @property
    def approvals(self) -> InMemoryApprovalRepository:
        if self._approvals is None:
            raise RuntimeError("unit of work must be entered before accessing repositories")
        return self._approvals

    @property
    def attempts(self) -> InMemoryExecutionAttemptRepository:
        if self._attempts is None:
            raise RuntimeError("unit of work must be entered before accessing repositories")
        return self._attempts

    @property
    def audits(self) -> InMemoryAuditRepository:
        if self._audits is None:
            raise RuntimeError("unit of work must be entered before accessing repositories")
        return self._audits

    async def __aenter__(self) -> InMemoryExecutionUnitOfWork:
        await self._lock.acquire()
        execution_store, attempt_store, approval_store, audit_store = self._stores
        self._working = (
            dict(execution_store),
            dict(attempt_store),
            dict(approval_store),
            dict(audit_store),
        )
        executions, attempts, approvals, audits = self._working
        self._executions = InMemoryToolExecutionRepository(executions)
        self._attempts = InMemoryExecutionAttemptRepository(attempts)
        self._approvals = InMemoryApprovalRepository(approvals)
        self._audits = InMemoryAuditRepository(audits)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        _ = (exc_type, exc_value, traceback)
        self._working = None
        self._executions = None
        self._attempts = None
        self._approvals = None
        self._audits = None
        self._lock.release()

    async def commit(self) -> None:
        executions, attempts, approvals, audits = self._require_working()
        execution_store, attempt_store, approval_store, audit_store = self._stores
        execution_store.clear()
        execution_store.update(executions)
        attempt_store.clear()
        attempt_store.update(attempts)
        approval_store.clear()
        approval_store.update(approvals)
        audit_store.clear()
        audit_store.update(audits)

    async def rollback(self) -> None:
        executions, attempts, approvals, audits = self._require_working()
        execution_store, attempt_store, approval_store, audit_store = self._stores
        executions.clear()
        executions.update(execution_store)
        attempts.clear()
        attempts.update(attempt_store)
        approvals.clear()
        approvals.update(approval_store)
        audits.clear()
        audits.update(audit_store)

    def _require_working(
        self,
    ) -> tuple[
        dict[str, ToolExecution],
        dict[str, ExecutionAttempt],
        dict[str, ApprovalRequest],
        dict[str, AuditEvent],
    ]:
        if self._working is None:
            raise RuntimeError("unit of work must be entered before transaction control")
        return self._working


class InMemoryExecutionUnitOfWorkFactory:
    def __init__(self) -> None:
        self._executions: dict[str, ToolExecution] = {}
        self._attempts: dict[str, ExecutionAttempt] = {}
        self._approvals: dict[str, ApprovalRequest] = {}
        self._audits: dict[str, AuditEvent] = {}
        self._lock = asyncio.Lock()

    def __call__(self) -> InMemoryExecutionUnitOfWork:
        return InMemoryExecutionUnitOfWork(
            execution_store=self._executions,
            attempt_store=self._attempts,
            approval_store=self._approvals,
            audit_store=self._audits,
            lock=self._lock,
        )

    @property
    def execution_reader(self) -> InMemoryToolExecutionRepository:
        return InMemoryToolExecutionRepository(self._executions)

    @property
    def audit_reader(self) -> InMemoryAuditRepository:
        return InMemoryAuditRepository(self._audits)

    @property
    def attempt_reader(self) -> InMemoryExecutionAttemptRepository:
        return InMemoryExecutionAttemptRepository(self._attempts)
