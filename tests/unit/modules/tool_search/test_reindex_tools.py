"""Reindex 的 Digest 去重、Batch、Dry Run 与 Stale Upsert 测试。"""

from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta

import pytest

from nexusmcp.modules.catalog.adapters.in_memory import InMemoryToolCatalogRepository
from nexusmcp.modules.catalog.domain import PublishedTool, ToolSideEffect, ToolVisibility
from nexusmcp.modules.tool_search.adapters.in_memory import (
    InMemoryToolSearchUnitOfWorkFactory,
)
from nexusmcp.modules.tool_search.document_builder import ToolSearchDocumentBuilder
from nexusmcp.modules.tool_search.domain import EmbeddingVector
from nexusmcp.modules.tool_search.reindex_tools import ReindexTools, ReindexToolsCommand
from nexusmcp.shared.request_context import ActorContext


@dataclass(slots=True)
class SteppingClock:
    current: datetime = datetime(2026, 8, 27, tzinfo=UTC)

    def now(self) -> datetime:
        value = self.current
        self.current += timedelta(seconds=1)
        return value


class SequentialIdentifierGenerator:
    def __init__(self) -> None:
        self._value = 0

    def new_id(self) -> str:
        self._value += 1
        return f"embedding-{self._value}"


class FakeEmbeddingProvider:
    model = "test/embedding"
    dimensions = 3

    def __init__(self) -> None:
        self.batches: list[tuple[str, ...]] = []

    async def embed(self, texts: tuple[str, ...]) -> tuple[EmbeddingVector, ...]:
        self.batches.append(texts)
        return tuple(
            EmbeddingVector(
                model=self.model,
                dimensions=self.dimensions,
                values=(float(index + 1), 0.0, 0.0),
            )
            for index, _text in enumerate(texts)
        )


def published_tool(
    tool_id: str,
    name: str,
    description: str,
) -> PublishedTool:
    return PublishedTool(
        tool_id=tool_id,
        tool_version_id=f"{tool_id}-v1",
        tenant_id="tenant-a",
        canonical_name=name,
        display_name=name.replace(".", " ").title(),
        description=description,
        input_schema={"type": "object", "properties": {}},
        output_schema=None,
        version=1,
        visibility=ToolVisibility.PUBLIC,
        side_effect=ToolSideEffect.READ_ONLY,
        schema_digest="1" * 64,
        owner="platform",
        tags=("tool",),
    )


def context() -> ActorContext:
    return ActorContext(
        request_id="request-reindex",
        trace_id="a" * 32,
        tenant_id="tenant-a",
        principal_id="admin-a",
        authn_method="test",
    )


def use_case(
    tools: tuple[PublishedTool, ...],
    factory: InMemoryToolSearchUnitOfWorkFactory,
    provider: FakeEmbeddingProvider | None,
    identifiers: SequentialIdentifierGenerator,
) -> ReindexTools:
    return ReindexTools(
        published_tools=InMemoryToolCatalogRepository(published_tools=tools),
        unit_of_work_factory=factory,
        document_builder=ToolSearchDocumentBuilder(),
        embedding_provider=provider,
        embedding_model="test/embedding",
        embedding_dimensions=3,
        clock=SteppingClock(),
        identifier_generator=identifiers,
    )


@pytest.mark.asyncio
async def test_reindex_skips_current_digest_and_updates_only_stale_tool() -> None:
    first = published_tool("tool-a", "directory.get_employee", "Get one employee.")
    second = published_tool("tool-b", "inventory.get_status", "Get inventory status.")
    factory = InMemoryToolSearchUnitOfWorkFactory()
    provider = FakeEmbeddingProvider()
    identifiers = SequentialIdentifierGenerator()
    indexer = use_case((first, second), factory, provider, identifiers)

    initial = await indexer.execute(ReindexToolsCommand(context=context(), batch_size=1))
    repeated = await indexer.execute(ReindexToolsCommand(context=context()))
    changed_first = replace(first, description="Get one employee and contact details.")
    changed = await use_case(
        (changed_first, second),
        factory,
        provider,
        identifiers,
    ).execute(ReindexToolsCommand(context=context()))

    stored = await factory.reader.list_by_tool_versions(
        "tenant-a",
        (first.tool_version_id, second.tool_version_id),
        embedding_model="test/embedding",
        embedding_dimensions=3,
    )
    assert initial.embedded_count == 2 and initial.batch_count == 2
    assert repeated.current_count == 2 and repeated.embedded_count == 0
    assert changed.current_count == 1 and changed.embedded_count == 1
    assert len(provider.batches) == 3
    assert len(stored) == 2
    changed_projection = next(
        embedding for embedding in stored if embedding.tool_version_id == first.tool_version_id
    )
    assert changed_projection.id == "embedding-1"


@pytest.mark.asyncio
async def test_dry_run_reads_digest_state_without_provider_or_writes() -> None:
    tool = published_tool("tool-a", "directory.get_employee", "Get one employee.")
    factory = InMemoryToolSearchUnitOfWorkFactory()
    identifiers = SequentialIdentifierGenerator()
    provider = FakeEmbeddingProvider()
    await use_case((tool,), factory, provider, identifiers).execute(
        ReindexToolsCommand(context=context())
    )

    result = await use_case((tool,), factory, None, identifiers).execute(
        ReindexToolsCommand(context=context(), dry_run=True)
    )

    assert result.current_count == 1
    assert result.pending_count == 0
    assert result.embedded_count == 0
    assert result.dry_run is True
