"""Audit 追加写入 Port。"""

from typing import Protocol

from nexusmcp.modules.audit.domain import AuditEvent


class AuditSink(Protocol):
    async def append(self, event: AuditEvent) -> None: ...


class AuditRepository(AuditSink, Protocol):
    async def list_by_tenant(self, tenant_id: str) -> tuple[AuditEvent, ...]: ...

    async def list_by_execution(
        self,
        tenant_id: str,
        execution_id: str,
    ) -> tuple[AuditEvent, ...]: ...
