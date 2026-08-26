"""用于单元测试和单进程演示的事务型 InMemory Approval Adapter。"""

from __future__ import annotations

import asyncio
from types import TracebackType

from nexusmcp.modules.approval.domain import ApprovalRequest
from nexusmcp.modules.audit.adapters.in_memory import InMemoryAuditRepository
from nexusmcp.modules.audit.domain import AuditEvent
from nexusmcp.shared.errors import TenantBoundaryViolationError


class InMemoryApprovalRepository:
    def __init__(self, approvals: dict[str, ApprovalRequest]) -> None:
        self._approvals = approvals

    async def add(self, tenant_id: str, approval: ApprovalRequest) -> None:
        _require_tenant(tenant_id, approval)
        if approval.id in self._approvals:
            raise ValueError("approval already exists")
        self._approvals[approval.id] = approval

    async def get_for_update(
        self,
        tenant_id: str,
        approval_id: str,
    ) -> ApprovalRequest | None:
        return await self.get_by_id(tenant_id, approval_id)

    async def get_by_id(
        self,
        tenant_id: str,
        approval_id: str,
    ) -> ApprovalRequest | None:
        approval = self._approvals.get(approval_id)
        if approval is None or approval.tenant_id != tenant_id:
            return None
        return approval

    async def save(self, tenant_id: str, approval: ApprovalRequest) -> None:
        _require_tenant(tenant_id, approval)
        current = self._approvals.get(approval.id)
        if current is None or current.tenant_id != tenant_id:
            raise ValueError("approval does not exist in tenant")
        self._approvals[approval.id] = approval


class InMemoryApprovalUnitOfWork:
    def __init__(
        self,
        store: dict[str, ApprovalRequest],
        audit_store: dict[str, AuditEvent],
        lock: asyncio.Lock,
    ) -> None:
        self._store = store
        self._audit_store = audit_store
        self._lock = lock
        self._working: dict[str, ApprovalRequest] | None = None
        self._working_audits: dict[str, AuditEvent] | None = None
        self._approvals: InMemoryApprovalRepository | None = None
        self._audits: InMemoryAuditRepository | None = None

    @property
    def approvals(self) -> InMemoryApprovalRepository:
        if self._approvals is None:
            raise RuntimeError("unit of work must be entered before accessing repository")
        return self._approvals

    @property
    def audits(self) -> InMemoryAuditRepository:
        if self._audits is None:
            raise RuntimeError("unit of work must be entered before accessing repository")
        return self._audits

    async def __aenter__(self) -> InMemoryApprovalUnitOfWork:
        await self._lock.acquire()
        self._working = dict(self._store)
        self._working_audits = dict(self._audit_store)
        self._approvals = InMemoryApprovalRepository(self._working)
        self._audits = InMemoryAuditRepository(self._working_audits)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        _ = (exc_type, exc_value, traceback)
        self._working = None
        self._working_audits = None
        self._approvals = None
        self._audits = None
        self._lock.release()

    async def commit(self) -> None:
        working = self._require_working()
        self._store.clear()
        self._store.update(working)
        working_audits = self._require_working_audits()
        self._audit_store.clear()
        self._audit_store.update(working_audits)

    async def rollback(self) -> None:
        working = self._require_working()
        working.clear()
        working.update(self._store)
        working_audits = self._require_working_audits()
        working_audits.clear()
        working_audits.update(self._audit_store)

    def _require_working(self) -> dict[str, ApprovalRequest]:
        if self._working is None:
            raise RuntimeError("unit of work must be entered before transaction control")
        return self._working

    def _require_working_audits(self) -> dict[str, AuditEvent]:
        if self._working_audits is None:
            raise RuntimeError("unit of work must be entered before transaction control")
        return self._working_audits


class InMemoryApprovalUnitOfWorkFactory:
    """全局 Lock 只服务测试；PostgreSQL Adapter 使用行级 `FOR UPDATE`。"""

    def __init__(self) -> None:
        self._store: dict[str, ApprovalRequest] = {}
        self._audit_store: dict[str, AuditEvent] = {}
        self._lock = asyncio.Lock()

    def __call__(self) -> InMemoryApprovalUnitOfWork:
        return InMemoryApprovalUnitOfWork(self._store, self._audit_store, self._lock)


def _require_tenant(tenant_id: str, approval: ApprovalRequest) -> None:
    if approval.tenant_id != tenant_id:
        raise TenantBoundaryViolationError("approval crossed tenant boundary")
