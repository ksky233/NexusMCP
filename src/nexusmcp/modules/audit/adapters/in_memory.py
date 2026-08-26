"""测试使用的 Append-Only InMemory Audit Repository。"""

from nexusmcp.modules.audit.domain import AuditEvent


class InMemoryAuditRepository:
    def __init__(self, events: dict[str, AuditEvent] | None = None) -> None:
        self._events = events if events is not None else {}

    async def append(self, event: AuditEvent) -> None:
        if event.id in self._events:
            raise ValueError("audit event id already exists")
        self._events[event.id] = event

    async def list_by_tenant(self, tenant_id: str) -> tuple[AuditEvent, ...]:
        return tuple(event for event in self._events.values() if event.tenant_id == tenant_id)

    async def list_by_execution(
        self,
        tenant_id: str,
        execution_id: str,
    ) -> tuple[AuditEvent, ...]:
        return tuple(
            event
            for event in self._events.values()
            if event.tenant_id == tenant_id and event.execution_id == execution_id
        )
