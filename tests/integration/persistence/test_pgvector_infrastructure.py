"""pgvector Extension、2048 维 Round-Trip 与 Exact Cosine Search。"""

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from nexusmcp.modules.catalog.adapters.sqlalchemy_embedding_models import (
    TOOL_EMBEDDING_DIMENSIONS,
    ToolSearchEmbeddingModel,
)
from tests.contract.repositories.contracts import TENANT_A_ID, VERSION_ID
from tests.integration.persistence.test_mcp_read_only_http_call import seed_executable_tool

pytestmark = pytest.mark.integration


def basis_vector(index: int) -> list[float]:
    vector = [0.0] * TOOL_EMBEDDING_DIMENSIONS
    vector[index] = 1.0
    return vector


@pytest.mark.asyncio
async def test_pgvector_2048_round_trip_and_exact_cosine_search(
    pg_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with pg_session_factory() as seed_session:
        await seed_executable_tool(seed_session)
    near_id = uuid.UUID("00000000-0000-0000-0000-000000000081")
    far_id = uuid.UUID("00000000-0000-0000-0000-000000000082")
    indexed_at = datetime(2026, 8, 26, 23, 55, tzinfo=UTC)
    async with pg_session_factory() as session:
        extension_version = await session.scalar(
            text("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
        )
        session.add_all(
            [
                ToolSearchEmbeddingModel(
                    id=near_id,
                    tenant_id=uuid.UUID(TENANT_A_ID),
                    tool_version_id=uuid.UUID(VERSION_ID),
                    embedding_model="Qwen/Qwen3-Embedding-8B",
                    embedding_dimensions=TOOL_EMBEDDING_DIMENSIONS,
                    source_digest="a" * 64,
                    embedding=basis_vector(0),
                    indexed_at=indexed_at,
                ),
                ToolSearchEmbeddingModel(
                    id=far_id,
                    tenant_id=uuid.UUID(TENANT_A_ID),
                    tool_version_id=uuid.UUID(VERSION_ID),
                    embedding_model="test/far-vector",
                    embedding_dimensions=TOOL_EMBEDDING_DIMENSIONS,
                    source_digest="b" * 64,
                    embedding=basis_vector(1),
                    indexed_at=indexed_at,
                ),
            ]
        )
        await session.commit()

        dimensions = await session.scalar(
            select(func.vector_dims(ToolSearchEmbeddingModel.embedding)).where(
                ToolSearchEmbeddingModel.id == near_id
            )
        )
        nearest = await session.scalar(
            select(ToolSearchEmbeddingModel)
            .order_by(ToolSearchEmbeddingModel.embedding.cosine_distance(basis_vector(0)))
            .limit(1)
        )

    assert extension_version == "0.8.6"
    assert dimensions == TOOL_EMBEDDING_DIMENSIONS
    assert nearest is not None and nearest.id == near_id
    assert len(nearest.embedding) == TOOL_EMBEDDING_DIMENSIONS
    assert nearest.embedding[0] == pytest.approx(1.0)
