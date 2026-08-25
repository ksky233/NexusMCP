"""PublishedToolReader 的短 Session SQLAlchemy Adapter。"""

from nexusmcp.infrastructure.persistence.runtime import DatabaseRuntimePort
from nexusmcp.modules.catalog.adapters.sqlalchemy_repository import (
    SqlAlchemyToolCatalogRepository,
)
from nexusmcp.modules.catalog.domain import PublishedTool


class SqlAlchemyPublishedToolReader:
    """每次 Query 独立获取 Session，不跨 MCP 请求共享事务状态。"""

    def __init__(self, database_runtime: DatabaseRuntimePort) -> None:
        self._database_runtime = database_runtime

    async def list_published_by_tenant(self, tenant_id: str) -> tuple[PublishedTool, ...]:
        session_factory = self._database_runtime.require_session_factory()
        async with session_factory() as session:
            repository = SqlAlchemyToolCatalogRepository(session)
            return await repository.list_published_by_tenant(tenant_id)

    async def get_published_by_name(
        self,
        tenant_id: str,
        canonical_name: str,
    ) -> PublishedTool | None:
        session_factory = self._database_runtime.require_session_factory()
        async with session_factory() as session:
            repository = SqlAlchemyToolCatalogRepository(session)
            return await repository.get_published_by_name(tenant_id, canonical_name)
