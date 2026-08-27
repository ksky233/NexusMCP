"""Published Tool → Fake Embedding → PostgreSQL Upsert 的 Reindex Integration。"""

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from nexusmcp.infrastructure.identifiers import UuidIdentifierGenerator
from nexusmcp.infrastructure.persistence.runtime import DatabaseRuntime
from nexusmcp.modules.catalog.adapters.sqlalchemy_models import ToolVersionModel
from nexusmcp.modules.catalog.adapters.sqlalchemy_reader import SqlAlchemyPublishedToolReader
from nexusmcp.modules.tool_search.adapters.sqlalchemy_models import TOOL_EMBEDDING_DIMENSIONS
from nexusmcp.modules.tool_search.adapters.sqlalchemy_uow import (
    SqlAlchemyToolSearchUnitOfWorkFactory,
)
from nexusmcp.modules.tool_search.document_builder import ToolSearchDocumentBuilder
from nexusmcp.modules.tool_search.domain import EmbeddingVector
from nexusmcp.modules.tool_search.reindex_tools import ReindexTools, ReindexToolsCommand
from nexusmcp.shared.request_context import ActorContext
from tests.contract.repositories.contracts import TENANT_A_ID, VERSION_ID
from tests.integration.persistence.test_mcp_read_only_http_call import seed_executable_tool

pytestmark = pytest.mark.integration


class FixedClock:
    def now(self) -> datetime:
        return datetime(2026, 8, 27, 1, 0, tzinfo=UTC)


class FakeQwenProvider:
    model = "Qwen/Qwen3-Embedding-8B"
    dimensions = TOOL_EMBEDDING_DIMENSIONS

    def __init__(self) -> None:
        self.calls = 0

    async def embed(self, texts: tuple[str, ...]) -> tuple[EmbeddingVector, ...]:
        self.calls += 1
        return tuple(
            EmbeddingVector(
                model=self.model,
                dimensions=self.dimensions,
                values=(1.0, *([0.0] * (self.dimensions - 1))),
            )
            for _text in texts
        )


def context() -> ActorContext:
    return ActorContext(
        request_id="request-postgresql-reindex",
        trace_id="a" * 32,
        tenant_id=TENANT_A_ID,
        principal_id="admin-a",
        authn_method="test",
    )


@pytest.mark.asyncio
async def test_postgresql_reindex_is_idempotent_and_updates_stale_digest(
    pg_session_factory: async_sessionmaker[AsyncSession],
    migrated_database_url: str,
) -> None:
    async with pg_session_factory() as seed_session:
        await seed_executable_tool(seed_session)
    runtime = DatabaseRuntime(migrated_database_url)
    await runtime.start()
    provider = FakeQwenProvider()
    try:
        factory = SqlAlchemyToolSearchUnitOfWorkFactory(runtime.require_session_factory())
        use_case = ReindexTools(
            published_tools=SqlAlchemyPublishedToolReader(runtime),
            unit_of_work_factory=factory,
            document_builder=ToolSearchDocumentBuilder(),
            embedding_provider=provider,
            embedding_model=provider.model,
            embedding_dimensions=provider.dimensions,
            clock=FixedClock(),
            identifier_generator=UuidIdentifierGenerator(),
        )
        initial = await use_case.execute(ReindexToolsCommand(context=context()))
        repeated = await use_case.execute(ReindexToolsCommand(context=context()))
        async with factory() as unit_of_work:
            before = await unit_of_work.embeddings.list_by_tool_versions(
                TENANT_A_ID,
                (VERSION_ID,),
                embedding_model=provider.model,
                embedding_dimensions=provider.dimensions,
            )

        async with pg_session_factory() as session:
            await session.execute(
                update(ToolVersionModel)
                .where(ToolVersionModel.id == uuid.UUID(VERSION_ID))
                .values(
                    description="Get one employee and contact details.",
                    search_description="Get one employee and contact details.",
                )
            )
            await session.commit()
        changed = await use_case.execute(ReindexToolsCommand(context=context()))
        async with factory() as unit_of_work:
            after = await unit_of_work.embeddings.list_by_tool_versions(
                TENANT_A_ID,
                (VERSION_ID,),
                embedding_model=provider.model,
                embedding_dimensions=provider.dimensions,
            )
    finally:
        await runtime.stop()

    assert initial.embedded_count == 1
    assert repeated.current_count == 1 and repeated.embedded_count == 0
    assert changed.pending_count == 1 and changed.embedded_count == 1
    assert provider.calls == 2
    assert len(before) == len(after) == 1
    assert before[0].id == after[0].id
    assert before[0].source_digest != after[0].source_digest
    assert len(after[0].vector.values) == TOOL_EMBEDDING_DIMENSIONS
