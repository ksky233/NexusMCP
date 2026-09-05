"""PostgreSQL 公开演示工作区重置 Adapter。"""

import logging

from sqlalchemy import insert, text

from nexusmcp.infrastructure.persistence.identifiers import as_uuid
from nexusmcp.infrastructure.persistence.runtime import DatabaseRuntimePort
from nexusmcp.modules.identity.adapters.sqlalchemy_models import TenantModel

logger = logging.getLogger(__name__)

# 当前 Public Demo 是独立单 Tenant Database，TRUNCATE 可以原子恢复干净基线并保持 Schema/Migration。
_TRUNCATE_DEMO_WORKSPACE = text(
    """
    TRUNCATE TABLE
        tool_search_reindex_job,
        tool_search_embedding,
        audit_event,
        execution_attempt,
        tool_execution,
        approval_request,
        tool_binding,
        imported_operation,
        openapi_import_job,
        tool_version,
        tool,
        upstream_service,
        tenant
    CASCADE
    """
)


class SqlAlchemyDemoWorkspaceResetter:
    """只供独立 Public Demo Database 使用的全业务状态 Reset Adapter。"""

    def __init__(
        self,
        database_runtime: DatabaseRuntimePort,
        *,
        tenant_name: str = "NexusMCP Public Demo",
    ) -> None:
        self._database_runtime = database_runtime
        self._tenant_name = tenant_name

    async def reset(self, tenant_id: str) -> None:
        session_factory = self._database_runtime.require_session_factory()
        async with session_factory() as session, session.begin():
            await session.execute(_TRUNCATE_DEMO_WORKSPACE)
            await session.execute(
                insert(TenantModel).values(
                    id=as_uuid(tenant_id, field_name="demo tenant id"),
                    name=self._tenant_name,
                    status="active",
                )
            )
        logger.warning(
            "public_demo_workspace_reset",
            extra={
                "event": "public_demo_workspace_reset",
                "tenant_id": tenant_id,
            },
        )
