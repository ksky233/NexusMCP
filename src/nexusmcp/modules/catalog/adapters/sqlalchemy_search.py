"""PublishedToolSearch 的 PostgreSQL FTS Adapter。"""

from sqlalchemy import desc, func, select

from nexusmcp.infrastructure.persistence.identifiers import as_uuid
from nexusmcp.infrastructure.persistence.runtime import DatabaseRuntimePort
from nexusmcp.modules.catalog.adapters.sqlalchemy_mapping import published_tool_from_models
from nexusmcp.modules.catalog.adapters.sqlalchemy_models import ToolModel, ToolVersionModel
from nexusmcp.modules.catalog.domain import (
    PublishedToolSearchHit,
    ToolSideEffect,
    ToolStatus,
    ToolVersionStatus,
    ToolVisibility,
)
from nexusmcp.modules.connectors.adapters.sqlalchemy_models import ToolBindingModel
from nexusmcp.modules.connectors.domain import ToolBindingStatus


class SqlAlchemyPublishedToolSearch:
    def __init__(self, database_runtime: DatabaseRuntimePort) -> None:
        self._database_runtime = database_runtime

    async def search_published(
        self,
        tenant_id: str,
        query_text: str,
        *,
        visibilities: tuple[ToolVisibility, ...],
        namespace: str | None,
        side_effect: ToolSideEffect | None,
        limit: int,
    ) -> tuple[PublishedToolSearchHit, ...]:
        session_factory = self._database_runtime.require_session_factory()
        tsquery = func.websearch_to_tsquery("simple", query_text)
        rank = func.ts_rank_cd(ToolVersionModel.search_vector, tsquery).label("rank")
        statement = (
            select(ToolModel, ToolVersionModel, rank)
            .join(ToolVersionModel, ToolVersionModel.tool_id == ToolModel.id)
            .join(ToolBindingModel, ToolBindingModel.tool_version_id == ToolVersionModel.id)
            .where(
                ToolModel.tenant_id == as_uuid(tenant_id, field_name="tenant id"),
                ToolVersionModel.tenant_id == as_uuid(tenant_id, field_name="tenant id"),
                ToolBindingModel.tenant_id == as_uuid(tenant_id, field_name="tenant id"),
                ToolModel.status == ToolStatus.ACTIVE.value,
                ToolVersionModel.status == ToolVersionStatus.PUBLISHED.value,
                ToolBindingModel.status == ToolBindingStatus.PUBLISHED.value,
                ToolVersionModel.visibility.in_(
                    tuple(visibility.value for visibility in visibilities)
                ),
                ToolVersionModel.search_vector.op("@@")(tsquery),
            )
            .order_by(desc(rank), ToolModel.canonical_name)
            .limit(limit)
        )
        if namespace is not None:
            statement = statement.where(ToolModel.namespace == namespace)
        if side_effect is not None:
            statement = statement.where(ToolVersionModel.side_effect == side_effect.value)
        async with session_factory() as session:
            rows = (await session.execute(statement)).tuples().all()
        return tuple(
            PublishedToolSearchHit(
                tool=published_tool_from_models(tool, version),
                rank=float(row_rank),
            )
            for tool, version, row_rank in rows
        )
