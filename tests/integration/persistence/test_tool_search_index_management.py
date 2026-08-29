"""W4.6 Index Status、异步 Reindex Job 与 Search Diagnostics 纵向验收。"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

import httpx2
import pytest
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from nexusmcp.bootstrap.app import create_app
from nexusmcp.bootstrap.config import Settings
from nexusmcp.infrastructure.persistence.runtime import DatabaseRuntime
from nexusmcp.modules.identity.adapters.sqlalchemy_models import TenantModel
from nexusmcp.modules.tool_search.adapters.sqlalchemy_job_store import (
    SqlAlchemyToolSearchReindexJobStore,
)
from nexusmcp.modules.tool_search.domain import EmbeddingVector
from nexusmcp.modules.tool_search.index_management import (
    ToolSearchReindexJob,
    ToolSearchReindexJobStatus,
)
from nexusmcp.shared.errors import ToolSearchReindexJobConflictError
from tests.contract.repositories.contracts import TENANT_A_ID
from tests.integration.persistence.test_mcp_read_only_http_call import seed_executable_tool

pytestmark = pytest.mark.integration

MODEL = "test/w4-6-embedding"
DIMENSIONS = 2048


@dataclass(slots=True)
class FixedEmbeddingProvider:
    model: str = MODEL
    dimensions: int = DIMENSIONS
    calls: list[tuple[str, ...]] = field(default_factory=list)

    async def embed(self, texts: tuple[str, ...]) -> tuple[EmbeddingVector, ...]:
        self.calls.append(texts)
        return tuple(
            EmbeddingVector(
                model=self.model,
                dimensions=self.dimensions,
                values=(1.0, *([0.0] * (self.dimensions - 1))),
            )
            for _text in texts
        )


@pytest.mark.asyncio
async def test_admin_reindex_job_persists_projection_and_exposes_rrf_diagnostics(
    pg_session_factory: async_sessionmaker[AsyncSession],
    migrated_database_url: str,
) -> None:
    async with pg_session_factory() as session:
        await seed_executable_tool(session, upstream_endpoint="http://127.0.0.1:9001")
    provider = FixedEmbeddingProvider()
    app = create_app(
        Settings(
            environment="test",
            catalog_backend="postgresql",
            database_url=SecretStr(migrated_database_url),
            local_tenant_id=TENANT_A_ID,
            local_admin_principal_id="index-admin",
            control_plane_enabled=True,
            embedding_model=MODEL,
            embedding_dimensions=DIMENSIONS,
        ),
        embedding_provider=provider,
    )

    async with app.router.lifespan_context(app):
        async with httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            before = await client.get("/admin/tool-search/index-status")
            assert before.status_code == 200
            assert before.json()["missing_count"] == 1
            assert before.json()["embedding_available"] is True
            assert before.json()["items"][0]["state"] == "missing"

            created = await client.post(
                "/admin/tool-search/reindex-jobs",
                json={"force": False, "batch_size": 8},
            )
            assert created.status_code == 202
            job_id = created.json()["id"]

            job = await client.get(f"/admin/tool-search/reindex-jobs/{job_id}")
            assert job.status_code == 200
            assert job.json()["status"] == "succeeded"
            assert job.json()["embedded_count"] == 1
            assert len(provider.calls) == 1

            after = await client.get("/admin/tool-search/index-status")
            assert after.json()["current_count"] == 1
            assert after.json()["missing_count"] == 0
            assert after.json()["items"][0]["state"] == "current"

            search = await client.get(
                "/admin/search/tools",
                params={"q": "find a coworker", "retrieval_mode": "hybrid"},
            )
            assert search.status_code == 200
            hit = search.json()["hits"][0]
            assert hit["score_kind"] == "rrf"
            assert hit["rrf_score"] == pytest.approx(1 / 61)
            assert hit["lexical_rank"] is None
            assert hit["vector_rank"] == 1
            assert hit["vector_cosine_similarity"] == pytest.approx(1.0)

            repeated = await client.post("/admin/tool-search/reindex-jobs", json={})
            assert repeated.status_code == 202
            repeated_job = await client.get(
                f"/admin/tool-search/reindex-jobs/{repeated.json()['id']}"
            )
            assert repeated_job.json()["embedded_count"] == 0
            assert repeated_job.json()["current_count"] == 1
            assert len(provider.calls) == 2  # 第二次调用来自 Hybrid Query Embedding。

            jobs = await client.get("/admin/tool-search/reindex-jobs")
            assert jobs.json()["page"]["total"] == 2
            assert [item["status"] for item in jobs.json()["items"]] == [
                "succeeded",
                "succeeded",
            ]


@pytest.mark.asyncio
async def test_reindex_job_store_deduplicates_active_job_and_recovers_restart(
    pg_session_factory: async_sessionmaker[AsyncSession],
    migrated_database_url: str,
) -> None:
    async with pg_session_factory() as session:
        session.add(
            TenantModel(
                id=uuid.UUID(TENANT_A_ID),
                name="Reindex Job Tenant",
                status="active",
            )
        )
        await session.commit()
    runtime = DatabaseRuntime(migrated_database_url)
    await runtime.start()
    store = SqlAlchemyToolSearchReindexJobStore(runtime)
    now = datetime(2026, 8, 29, tzinfo=UTC)
    try:
        first = reindex_job("00000000-0000-0000-0000-000000000911", now)
        second = reindex_job("00000000-0000-0000-0000-000000000912", now)
        await store.create(first)
        with pytest.raises(ToolSearchReindexJobConflictError):
            await store.create(second)

        assert await store.recover_interrupted(TENANT_A_ID, finished_at=now) == 1
        recovered = await store.get(TENANT_A_ID, first.id)
        assert recovered is not None
        assert recovered.status is ToolSearchReindexJobStatus.FAILED
        assert recovered.error_code == "reindex_job_interrupted"

        await store.create(second)
    finally:
        await runtime.stop()


def reindex_job(job_id: str, created_at: datetime) -> ToolSearchReindexJob:
    return ToolSearchReindexJob(
        id=job_id,
        tenant_id=TENANT_A_ID,
        requested_by="index-admin",
        status=ToolSearchReindexJobStatus.PENDING,
        force=False,
        batch_size=16,
        embedding_model=MODEL,
        embedding_dimensions=DIMENSIONS,
        published_count=0,
        current_count=0,
        pending_count=0,
        embedded_count=0,
        batch_count=0,
        error_code=None,
        created_at=created_at,
    )
