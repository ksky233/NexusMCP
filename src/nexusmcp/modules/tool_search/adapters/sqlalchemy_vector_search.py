"""VectorToolSearch 的 PostgreSQL pgvector Exact Scan Adapter。"""

from sqlalchemy import and_, func, select

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
from nexusmcp.modules.tool_search.adapters.sqlalchemy_models import ToolSearchEmbeddingModel
from nexusmcp.modules.tool_search.domain import EmbeddingVector, VectorSearchResult


class SqlAlchemyExactVectorToolSearch:
    def __init__(self, database_runtime: DatabaseRuntimePort) -> None:
        self._database_runtime = database_runtime

    async def search_published_by_vector(
        self,
        tenant_id: str,
        query_vector: EmbeddingVector,
        *,
        visibilities: tuple[ToolVisibility, ...],
        eligible_tool_ids: tuple[str, ...] | None,
        namespace: str | None,
        side_effect: ToolSideEffect | None,
        limit: int,
    ) -> VectorSearchResult:
        if not visibilities or eligible_tool_ids == ():
            return VectorSearchResult(hits=(), eligible_count=0, indexed_count=0)
        tenant_uuid = as_uuid(tenant_id, field_name="tenant id")
        scope_filters = (
            ToolModel.tenant_id == tenant_uuid,
            ToolVersionModel.tenant_id == tenant_uuid,
            ToolBindingModel.tenant_id == tenant_uuid,
            ToolModel.status == ToolStatus.ACTIVE.value,
            ToolVersionModel.status == ToolVersionStatus.PUBLISHED.value,
            ToolBindingModel.status == ToolBindingStatus.PUBLISHED.value,
            ToolVersionModel.visibility.in_(tuple(item.value for item in visibilities)),
        )
        embedding_join = and_(
            ToolSearchEmbeddingModel.tool_version_id == ToolVersionModel.id,
            ToolSearchEmbeddingModel.tenant_id == tenant_uuid,
            ToolSearchEmbeddingModel.embedding_model == query_vector.model,
            ToolSearchEmbeddingModel.embedding_dimensions == query_vector.dimensions,
        )
        coverage_statement = (
            select(
                func.count(func.distinct(ToolVersionModel.id)),
                func.count(func.distinct(ToolSearchEmbeddingModel.tool_version_id)),
            )
            .select_from(ToolModel)
            .join(ToolVersionModel, ToolVersionModel.tool_id == ToolModel.id)
            .join(ToolBindingModel, ToolBindingModel.tool_version_id == ToolVersionModel.id)
            .outerjoin(ToolSearchEmbeddingModel, embedding_join)
            .where(*scope_filters)
        )
        distance = ToolSearchEmbeddingModel.embedding.cosine_distance(
            list(query_vector.values)
        ).label("distance")
        candidate_statement = (
            select(ToolModel, ToolVersionModel, distance)
            .join(ToolVersionModel, ToolVersionModel.tool_id == ToolModel.id)
            .join(ToolBindingModel, ToolBindingModel.tool_version_id == ToolVersionModel.id)
            .join(ToolSearchEmbeddingModel, embedding_join)
            .where(*scope_filters)
            .order_by(distance.asc(), ToolModel.canonical_name)
            .limit(limit)
        )
        if namespace is not None:
            coverage_statement = coverage_statement.where(ToolModel.namespace == namespace)
            candidate_statement = candidate_statement.where(ToolModel.namespace == namespace)
        if eligible_tool_ids is not None:
            eligible_ids = tuple(
                as_uuid(tool_id, field_name="eligible tool id") for tool_id in eligible_tool_ids
            )
            coverage_statement = coverage_statement.where(ToolModel.id.in_(eligible_ids))
            candidate_statement = candidate_statement.where(ToolModel.id.in_(eligible_ids))
        if side_effect is not None:
            coverage_statement = coverage_statement.where(
                ToolVersionModel.side_effect == side_effect.value
            )
            candidate_statement = candidate_statement.where(
                ToolVersionModel.side_effect == side_effect.value
            )

        session_factory = self._database_runtime.require_session_factory()
        async with session_factory() as session:
            eligible_count, indexed_count = (await session.execute(coverage_statement)).one()
            rows = (await session.execute(candidate_statement)).tuples().all()
        return VectorSearchResult(
            hits=tuple(
                PublishedToolSearchHit(
                    tool=published_tool_from_models(tool, version),
                    rank=1.0 - float(row_distance),
                )
                for tool, version, row_distance in rows
            ),
            eligible_count=int(eligible_count),
            indexed_count=int(indexed_count),
        )
