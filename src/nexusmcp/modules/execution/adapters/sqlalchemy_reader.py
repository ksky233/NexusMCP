"""由 DatabaseRuntime 创建短 Session 的 Execution/Audit Query Adapter。"""

from nexusmcp.infrastructure.persistence.runtime import DatabaseRuntimePort
from nexusmcp.modules.audit.adapters.sqlalchemy_repository import SqlAlchemyAuditRepository
from nexusmcp.modules.audit.domain import AuditEvent
from nexusmcp.modules.execution.adapters.sqlalchemy_repository import (
    SqlAlchemyToolExecutionRepository,
)
from nexusmcp.modules.execution.domain import ToolExecution


class SqlAlchemyToolExecutionReader:
    def __init__(self, database_runtime: DatabaseRuntimePort) -> None:
        self._database_runtime = database_runtime

    async def list_by_tenant(self, tenant_id: str) -> tuple[ToolExecution, ...]:
        session_factory = self._database_runtime.require_session_factory()
        async with session_factory() as session:
            return await SqlAlchemyToolExecutionRepository(session).list_by_tenant(tenant_id)


class SqlAlchemyAuditEventReader:
    def __init__(self, database_runtime: DatabaseRuntimePort) -> None:
        self._database_runtime = database_runtime

    async def list_by_tenant(self, tenant_id: str) -> tuple[AuditEvent, ...]:
        session_factory = self._database_runtime.require_session_factory()
        async with session_factory() as session:
            return await SqlAlchemyAuditRepository(session).list_by_tenant(tenant_id)
