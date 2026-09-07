"""Query Embedding → pgvector Exact Cosine Search 的 PostgreSQL Integration。"""

import uuid
from datetime import UTC, datetime

import httpx2
import pytest
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from nexusmcp.bootstrap.app import create_app
from nexusmcp.bootstrap.config import Settings
from nexusmcp.infrastructure.persistence.runtime import DatabaseRuntime
from nexusmcp.modules.catalog.adapters.sqlalchemy_models import ToolModel, ToolVersionModel
from nexusmcp.modules.catalog.domain import ToolSideEffect
from nexusmcp.modules.catalog.search import SearchPublishedToolsQuery
from nexusmcp.modules.tool_search.adapters.sqlalchemy_models import TOOL_EMBEDDING_DIMENSIONS
from nexusmcp.modules.tool_search.adapters.sqlalchemy_repository import (
    SqlAlchemyToolSearchEmbeddingRepository,
)
from nexusmcp.modules.tool_search.adapters.sqlalchemy_vector_search import (
    SqlAlchemyExactVectorToolSearch,
)
from nexusmcp.modules.tool_search.domain import (
    EmbeddingVector,
    ToolSearchEmbedding,
)
from nexusmcp.modules.tool_search.vector_search import SearchVectorTools
from nexusmcp.modules.toolsets.adapters.sqlalchemy_repository import (
    SqlAlchemyToolsetRepository,
)
from nexusmcp.modules.toolsets.domain import Toolset, ToolsetDiscoveryMode
from nexusmcp.shared.errors import ToolSearchModeUnavailableError
from tests.contract.repositories.contracts import TENANT_A_ID
from tests.integration.persistence.test_postgresql_fts_search import (
    context,
    seed_search_catalog,
)

pytestmark = pytest.mark.integration

MODEL = "Qwen/Qwen3-Embedding-8B"
NOW = datetime(2026, 8, 27, 2, 0, tzinfo=UTC)


class FixedQueryEmbeddingProvider:
    model = MODEL
    dimensions = TOOL_EMBEDDING_DIMENSIONS

    def __init__(self, values: tuple[float, ...]) -> None:
        self._values = values
        self.calls: list[tuple[str, ...]] = []

    async def embed(self, texts: tuple[str, ...]) -> tuple[EmbeddingVector, ...]:
        self.calls.append(texts)
        return (
            EmbeddingVector(
                model=self.model,
                dimensions=self.dimensions,
                values=self._values,
            ),
        )


def vector(first: float, second: float) -> tuple[float, ...]:
    return (first, second, *([0.0] * (TOOL_EMBEDDING_DIMENSIONS - 2)))


async def seed_vector_projection(session: AsyncSession) -> None:
    rows = (
        (
            await session.execute(
                select(
                    ToolModel.canonical_name,
                    ToolVersionModel.id,
                    ToolVersionModel.tenant_id,
                ).join(ToolVersionModel, ToolVersionModel.tool_id == ToolModel.id)
            )
        )
        .tuples()
        .all()
    )
    values_by_name = {
        "inventory.get_status": vector(1.0, 0.0),
        "inventory.reserve_stock": vector(0.0, 1.0),
        "inventory.internal_reconciliation": vector(-1.0, 0.0),
        # 跨 Tenant 候选故意最相似，用于证明 SQL Scope 在排名前生效。
        "inventory.cross_tenant_stock": vector(1.0, 0.0),
    }
    embeddings = tuple(
        ToolSearchEmbedding(
            id=str(uuid.uuid4()),
            tenant_id=str(tenant_id),
            tool_version_id=str(version_id),
            embedding_model=MODEL,
            embedding_dimensions=TOOL_EMBEDDING_DIMENSIONS,
            source_digest="a" * 64,
            vector=EmbeddingVector(
                model=MODEL,
                dimensions=TOOL_EMBEDDING_DIMENSIONS,
                values=values_by_name[canonical_name],
            ),
            indexed_at=NOW,
        )
        for canonical_name, version_id, tenant_id in rows
        if canonical_name in values_by_name
    )
    repository = SqlAlchemyToolSearchEmbeddingRepository(session)
    by_tenant: dict[str, list[ToolSearchEmbedding]] = {}
    for embedding in embeddings:
        by_tenant.setdefault(embedding.tenant_id, []).append(embedding)
    for tenant_id, tenant_embeddings in by_tenant.items():
        await repository.upsert_many(tenant_id, tuple(tenant_embeddings))
    await session.commit()


@pytest.mark.asyncio
async def test_exact_vector_search_ranks_by_cosine_and_applies_governance_scope(
    pg_session_factory: async_sessionmaker[AsyncSession],
    migrated_database_url: str,
) -> None:
    async with pg_session_factory() as seed_session:
        await seed_search_catalog(seed_session)
        await seed_vector_projection(seed_session)
    runtime = DatabaseRuntime(migrated_database_url)
    await runtime.start()
    provider = FixedQueryEmbeddingProvider(vector(1.0, 0.0))
    try:
        search = SearchVectorTools(
            embedding_provider=provider,
            vector_search=SqlAlchemyExactVectorToolSearch(runtime),
        )
        result = await search.execute(
            SearchPublishedToolsQuery(
                context=context(TENANT_A_ID, "operator"),
                text="things that are almost sold out",
                namespace="inventory",
                side_effect=ToolSideEffect.READ_ONLY,
                limit=10,
            )
        )
    finally:
        await runtime.stop()

    assert [hit.tool.canonical_name for hit in result.hits] == [
        "inventory.get_status",
        "inventory.reserve_stock",
        "inventory.internal_reconciliation",
    ]
    assert result.hits[0].rank == pytest.approx(1.0)
    assert result.eligible_count == result.indexed_count == 3
    assert provider.calls == [("things that are almost sold out",)]
    assert all(hit.tool.tenant_id == TENANT_A_ID for hit in result.hits)


@pytest.mark.asyncio
async def test_exact_vector_search_reports_missing_projection_instead_of_fts_fallback(
    pg_session_factory: async_sessionmaker[AsyncSession],
    migrated_database_url: str,
) -> None:
    async with pg_session_factory() as seed_session:
        await seed_search_catalog(seed_session)
    runtime = DatabaseRuntime(migrated_database_url)
    await runtime.start()
    try:
        search = SearchVectorTools(
            embedding_provider=FixedQueryEmbeddingProvider(vector(1.0, 0.0)),
            vector_search=SqlAlchemyExactVectorToolSearch(runtime),
        )
        with pytest.raises(ToolSearchModeUnavailableError):
            await search.execute(
                SearchPublishedToolsQuery(
                    context=context(TENANT_A_ID, "operator"),
                    text="find a warehouse operation",
                )
            )
    finally:
        await runtime.stop()


@pytest.mark.asyncio
async def test_hybrid_search_is_exposed_through_built_in_meta_tool(
    pg_session_factory: async_sessionmaker[AsyncSession],
    migrated_database_url: str,
) -> None:
    async with pg_session_factory() as seed_session:
        await seed_search_catalog(seed_session)
        await seed_vector_projection(seed_session)
    provider = FixedQueryEmbeddingProvider(vector(1.0, 0.0))
    app = create_app(
        Settings(
            environment="test",
            catalog_backend="postgresql",
            database_url=SecretStr(migrated_database_url),
            local_tenant_id=TENANT_A_ID,
            tool_discovery_mode="search_first",
            embedding_api_key=None,
        ),
        embedding_provider=provider,
    )

    async with app.router.lifespan_context(app):
        transport = httpx2.ASGITransport(app=app)
        async with httpx2.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as http_client:
            mcp_transport = streamable_http_client(
                "http://testserver/mcp",
                http_client=http_client,
            )
            async with Client(mcp_transport) as client:
                listed = await client.list_tools(cache_mode="refresh")
                result = await client.call_tool(
                    "nexus.search_tools",
                    {
                        "query": "things that are almost sold out",
                        "retrieval_mode": "hybrid",
                        "limit": 3,
                    },
                )

    assert [tool.name for tool in listed.tools] == ["nexus.search_tools"]
    assert result.is_error is False
    assert result.structured_content["retrievalMode"] == "hybrid"
    assert result.structured_content["tools"][0]["name"] == "inventory.get_status"
    assert result.meta is not None
    assert result.meta["com.nexusmcp/indexVersion"] == f"{MODEL}@{TOOL_EMBEDDING_DIMENSIONS}"
    assert provider.calls == [("things that are almost sold out",)]


@pytest.mark.asyncio
async def test_scoped_hybrid_filters_fts_and_vector_candidates_before_rrf(
    pg_session_factory: async_sessionmaker[AsyncSession],
    migrated_database_url: str,
) -> None:
    async with pg_session_factory() as seed_session:
        await seed_search_catalog(seed_session)
        await seed_vector_projection(seed_session)
        reserve_tool_id = str(
            await seed_session.scalar(
                select(ToolModel.id).where(ToolModel.canonical_name == "inventory.reserve_stock")
            )
        )
        toolset = (
            Toolset.create_explicit(
                toolset_id="00000000-0000-0000-0000-000000000560",
                tenant_id=TENANT_A_ID,
                slug="inventory-writes",
                name="Inventory Writes",
                description=None,
                created_by="admin-a",
                created_at=NOW,
                discovery_mode=ToolsetDiscoveryMode.SEARCH_FIRST,
            )
            .replace_members(
                expected_revision=1,
                tool_ids=(reserve_tool_id,),
                actor_id="admin-a",
                occurred_at=NOW,
            )
            .replace_grants(
                expected_revision=2,
                principal_ids=("local-agent-service",),
                actor_id="admin-a",
                occurred_at=NOW,
            )
            .activate(expected_revision=3, activated_at=NOW)
        )
        await SqlAlchemyToolsetRepository(seed_session).add(TENANT_A_ID, toolset)
        await seed_session.commit()

    provider = FixedQueryEmbeddingProvider(vector(1.0, 0.0))
    app = create_app(
        Settings(
            environment="test",
            catalog_backend="postgresql",
            database_url=SecretStr(migrated_database_url),
            local_tenant_id=TENANT_A_ID,
            embedding_api_key=None,
        ),
        embedding_provider=provider,
    )

    async with app.router.lifespan_context(app):
        async with httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=app),
            base_url="http://testserver",
        ) as http_client:
            transport = streamable_http_client(
                "http://testserver/mcp/toolsets/inventory-writes",
                http_client=http_client,
            )
            async with Client(transport) as client:
                listed = await client.list_tools(cache_mode="refresh")
                result = await client.call_tool(
                    "nexus.search_tools",
                    {
                        "query": "inventory",
                        "retrieval_mode": "hybrid",
                        "limit": 3,
                    },
                )

    assert [tool.name for tool in listed.tools] == ["nexus.search_tools"]
    assert result.is_error is False
    assert [item["name"] for item in result.structured_content["tools"]] == [
        "inventory.reserve_stock"
    ]
    assert result.meta is not None
    assert result.meta["com.nexusmcp/candidateCount"] == 1
    assert provider.calls == [("inventory",)]
