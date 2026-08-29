"""Tool Search Projection 检查与异步 Reindex Job 用例。"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol

from nexusmcp.modules.catalog.ports import PublishedToolReader
from nexusmcp.modules.tool_search.document_builder import ToolSearchDocumentBuilder
from nexusmcp.modules.tool_search.ports import ToolSearchUnitOfWorkFactory
from nexusmcp.modules.tool_search.reindex_tools import (
    ReindexTools,
    ReindexToolsCommand,
    ReindexToolsResult,
)
from nexusmcp.shared.clock import Clock
from nexusmcp.shared.errors import (
    EmbeddingUnavailableError,
    NexusMcpError,
    ToolSearchReindexJobNotFoundError,
)
from nexusmcp.shared.identifiers import IdentifierGenerator
from nexusmcp.shared.request_context import ActorContext

logger = logging.getLogger(__name__)


class ToolSearchIndexState(StrEnum):
    MISSING = "missing"
    STALE = "stale"
    CURRENT = "current"


class ToolSearchReindexJobStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class ToolSearchIndexItem:
    tool_id: str
    tool_version_id: str
    canonical_name: str
    state: ToolSearchIndexState
    indexed_at: datetime | None


@dataclass(frozen=True, slots=True)
class ToolSearchIndexSnapshot:
    published_count: int
    current_count: int
    missing_count: int
    stale_count: int
    embedding_model: str
    embedding_dimensions: int
    embedding_available: bool
    items: tuple[ToolSearchIndexItem, ...]


@dataclass(frozen=True, slots=True)
class ToolSearchReindexJob:
    id: str
    tenant_id: str
    requested_by: str
    status: ToolSearchReindexJobStatus
    force: bool
    batch_size: int
    embedding_model: str
    embedding_dimensions: int
    published_count: int
    current_count: int
    pending_count: int
    embedded_count: int
    batch_count: int
    error_code: str | None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None


class ToolSearchReindexJobStore(Protocol):
    """Job Store Port；Adapter 必须原子保证每租户最多一个 Active Job。"""

    async def create(self, job: ToolSearchReindexJob) -> None: ...

    async def get(self, tenant_id: str, job_id: str) -> ToolSearchReindexJob | None: ...

    async def list_recent(
        self,
        tenant_id: str,
        *,
        offset: int,
        limit: int,
    ) -> tuple[tuple[ToolSearchReindexJob, ...], int]: ...

    async def claim(
        self,
        tenant_id: str,
        job_id: str,
        *,
        started_at: datetime,
    ) -> ToolSearchReindexJob | None: ...

    async def succeed(
        self,
        tenant_id: str,
        job_id: str,
        *,
        result: ReindexToolsResult,
        finished_at: datetime,
    ) -> None: ...

    async def fail(
        self,
        tenant_id: str,
        job_id: str,
        *,
        error_code: str,
        finished_at: datetime,
    ) -> None: ...

    async def recover_interrupted(
        self,
        tenant_id: str,
        *,
        finished_at: datetime,
    ) -> int: ...


class InspectToolSearchIndex:
    def __init__(
        self,
        *,
        published_tools: PublishedToolReader,
        unit_of_work_factory: ToolSearchUnitOfWorkFactory,
        document_builder: ToolSearchDocumentBuilder,
        embedding_model: str,
        embedding_dimensions: int,
        embedding_available: bool,
    ) -> None:
        self._published_tools = published_tools
        self._unit_of_work_factory = unit_of_work_factory
        self._document_builder = document_builder
        self._embedding_model = embedding_model
        self._embedding_dimensions = embedding_dimensions
        self._embedding_available = embedding_available

    async def execute(self, tenant_id: str) -> ToolSearchIndexSnapshot:
        tools = tuple(
            sorted(
                await self._published_tools.list_published_by_tenant(tenant_id),
                key=lambda item: item.canonical_name,
            )
        )
        documents = tuple(self._document_builder.build(tool) for tool in tools)
        async with self._unit_of_work_factory() as unit_of_work:
            embeddings = await unit_of_work.embeddings.list_by_tool_versions(
                tenant_id,
                tuple(document.tool_version_id for document in documents),
                embedding_model=self._embedding_model,
                embedding_dimensions=self._embedding_dimensions,
            )
        by_version = {embedding.tool_version_id: embedding for embedding in embeddings}
        items: list[ToolSearchIndexItem] = []
        for tool, document in zip(tools, documents, strict=True):
            embedding = by_version.get(document.tool_version_id)
            state = (
                ToolSearchIndexState.MISSING
                if embedding is None
                else (
                    ToolSearchIndexState.CURRENT
                    if embedding.source_digest == document.source_digest
                    else ToolSearchIndexState.STALE
                )
            )
            items.append(
                ToolSearchIndexItem(
                    tool_id=tool.tool_id,
                    tool_version_id=tool.tool_version_id,
                    canonical_name=tool.canonical_name,
                    state=state,
                    indexed_at=embedding.indexed_at if embedding is not None else None,
                )
            )
        current_count = sum(item.state is ToolSearchIndexState.CURRENT for item in items)
        missing_count = sum(item.state is ToolSearchIndexState.MISSING for item in items)
        stale_count = sum(item.state is ToolSearchIndexState.STALE for item in items)
        return ToolSearchIndexSnapshot(
            published_count=len(items),
            current_count=current_count,
            missing_count=missing_count,
            stale_count=stale_count,
            embedding_model=self._embedding_model,
            embedding_dimensions=self._embedding_dimensions,
            embedding_available=self._embedding_available,
            items=tuple(items),
        )


class CreateToolSearchReindexJob:
    def __init__(
        self,
        *,
        store: ToolSearchReindexJobStore,
        identifier_generator: IdentifierGenerator,
        clock: Clock,
        embedding_model: str,
        embedding_dimensions: int,
        embedding_available: bool,
    ) -> None:
        self._store = store
        self._identifier_generator = identifier_generator
        self._clock = clock
        self._embedding_model = embedding_model
        self._embedding_dimensions = embedding_dimensions
        self._embedding_available = embedding_available

    async def execute(
        self,
        context: ActorContext,
        *,
        force: bool,
        batch_size: int,
    ) -> ToolSearchReindexJob:
        if not self._embedding_available:
            raise EmbeddingUnavailableError("reindex job requires an embedding provider")
        if not 1 <= batch_size <= 64:
            raise ValueError("reindex job batch size must be between 1 and 64")
        job = ToolSearchReindexJob(
            id=self._identifier_generator.new_id(),
            tenant_id=context.tenant_id,
            requested_by=context.principal_id,
            status=ToolSearchReindexJobStatus.PENDING,
            force=force,
            batch_size=batch_size,
            embedding_model=self._embedding_model,
            embedding_dimensions=self._embedding_dimensions,
            published_count=0,
            current_count=0,
            pending_count=0,
            embedded_count=0,
            batch_count=0,
            error_code=None,
            created_at=self._clock.now(),
        )
        await self._store.create(job)
        return job


class RunToolSearchReindexJob:
    def __init__(
        self,
        *,
        store: ToolSearchReindexJobStore,
        reindex_tools: ReindexTools,
        clock: Clock,
    ) -> None:
        self._store = store
        self._reindex_tools = reindex_tools
        self._clock = clock

    async def execute(self, tenant_id: str, job_id: str) -> None:
        job = await self._store.claim(tenant_id, job_id, started_at=self._clock.now())
        if job is None:
            return
        try:
            result = await self._reindex_tools.execute(
                ReindexToolsCommand(
                    context=ActorContext(
                        request_id=job.id,
                        trace_id=job.id.replace("-", ""),
                        tenant_id=job.tenant_id,
                        principal_id=job.requested_by,
                        authn_method="admin_background_job",
                    ),
                    batch_size=job.batch_size,
                    force=job.force,
                )
            )
        except NexusMcpError as error:
            await self._store.fail(
                tenant_id,
                job_id,
                error_code=error.code,
                finished_at=self._clock.now(),
            )
            logger.warning(
                "tool_search_reindex_job_failed",
                extra={"event": "tool_search_reindex_job_failed", "error_code": error.code},
            )
        except Exception:
            await self._store.fail(
                tenant_id,
                job_id,
                error_code="internal_error",
                finished_at=self._clock.now(),
            )
            logger.exception(
                "tool_search_reindex_job_failed",
                extra={"event": "tool_search_reindex_job_failed", "error_code": "internal_error"},
            )
        else:
            await self._store.succeed(
                tenant_id,
                job_id,
                result=result,
                finished_at=self._clock.now(),
            )


class GetToolSearchReindexJob:
    def __init__(self, store: ToolSearchReindexJobStore) -> None:
        self._store = store

    async def execute(self, tenant_id: str, job_id: str) -> ToolSearchReindexJob:
        job = await self._store.get(tenant_id, job_id)
        if job is None:
            raise ToolSearchReindexJobNotFoundError(f"reindex job {job_id} was not found")
        return job


class ListToolSearchReindexJobs:
    def __init__(self, store: ToolSearchReindexJobStore) -> None:
        self._store = store

    async def execute(
        self,
        tenant_id: str,
        *,
        offset: int,
        limit: int,
    ) -> tuple[tuple[ToolSearchReindexJob, ...], int]:
        return await self._store.list_recent(tenant_id, offset=offset, limit=limit)
