"""ToolSearchEmbeddingRepository 的 PostgreSQL pgvector Adapter。"""

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from nexusmcp.infrastructure.persistence.identifiers import as_uuid
from nexusmcp.modules.tool_search.adapters.sqlalchemy_mapping import embedding_from_model
from nexusmcp.modules.tool_search.adapters.sqlalchemy_models import ToolSearchEmbeddingModel
from nexusmcp.modules.tool_search.domain import ToolSearchEmbedding
from nexusmcp.shared.errors import TenantBoundaryViolationError


class SqlAlchemyToolSearchEmbeddingRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_by_tool_versions(
        self,
        tenant_id: str,
        tool_version_ids: tuple[str, ...],
        *,
        embedding_model: str,
        embedding_dimensions: int,
    ) -> tuple[ToolSearchEmbedding, ...]:
        if not tool_version_ids:
            return ()
        models = (
            await self._session.scalars(
                select(ToolSearchEmbeddingModel).where(
                    ToolSearchEmbeddingModel.tenant_id
                    == as_uuid(tenant_id, field_name="tenant id"),
                    ToolSearchEmbeddingModel.tool_version_id.in_(
                        tuple(
                            as_uuid(tool_version_id, field_name="tool version id")
                            for tool_version_id in tool_version_ids
                        )
                    ),
                    ToolSearchEmbeddingModel.embedding_model == embedding_model,
                    ToolSearchEmbeddingModel.embedding_dimensions == embedding_dimensions,
                )
            )
        ).all()
        return tuple(embedding_from_model(model) for model in models)

    async def upsert_many(
        self,
        tenant_id: str,
        embeddings: tuple[ToolSearchEmbedding, ...],
    ) -> None:
        if not embeddings:
            return
        for embedding in embeddings:
            if embedding.tenant_id != tenant_id:
                raise TenantBoundaryViolationError("tool embedding crossed tenant boundary")
        statement = insert(ToolSearchEmbeddingModel).values(
            [
                {
                    "id": as_uuid(embedding.id, field_name="embedding id"),
                    "tenant_id": as_uuid(tenant_id, field_name="tenant id"),
                    "tool_version_id": as_uuid(
                        embedding.tool_version_id,
                        field_name="tool version id",
                    ),
                    "embedding_model": embedding.embedding_model,
                    "embedding_dimensions": embedding.embedding_dimensions,
                    "source_digest": embedding.source_digest,
                    "embedding": list(embedding.vector.values),
                    "indexed_at": embedding.indexed_at,
                }
                for embedding in embeddings
            ]
        )
        statement = statement.on_conflict_do_update(
            constraint="uq_tool_search_embedding_scope",
            set_={
                "source_digest": statement.excluded.source_digest,
                "embedding": statement.excluded.embedding,
                "indexed_at": statement.excluded.indexed_at,
            },
        )
        await self._session.execute(statement)
