"""Tool Search Reindex 单元测试使用的事务型 InMemory Adapter。"""

from __future__ import annotations

import asyncio
from types import TracebackType

from nexusmcp.modules.tool_search.domain import ToolSearchEmbedding
from nexusmcp.shared.errors import TenantBoundaryViolationError

type EmbeddingScope = tuple[str, str, str, int]


class InMemoryToolSearchEmbeddingRepository:
    def __init__(self, store: dict[EmbeddingScope, ToolSearchEmbedding]) -> None:
        self._store = store

    async def list_by_tool_versions(
        self,
        tenant_id: str,
        tool_version_ids: tuple[str, ...],
        *,
        embedding_model: str,
        embedding_dimensions: int,
    ) -> tuple[ToolSearchEmbedding, ...]:
        version_ids = set(tool_version_ids)
        return tuple(
            embedding
            for scope, embedding in self._store.items()
            if scope[0] == tenant_id
            and scope[1] in version_ids
            and scope[2] == embedding_model
            and scope[3] == embedding_dimensions
        )

    async def upsert_many(
        self,
        tenant_id: str,
        embeddings: tuple[ToolSearchEmbedding, ...],
    ) -> None:
        for embedding in embeddings:
            if embedding.tenant_id != tenant_id:
                raise TenantBoundaryViolationError("tool embedding crossed tenant boundary")
            scope = (
                tenant_id,
                embedding.tool_version_id,
                embedding.embedding_model,
                embedding.embedding_dimensions,
            )
            current = self._store.get(scope)
            persisted = (
                embedding
                if current is None
                else ToolSearchEmbedding(
                    id=current.id,
                    tenant_id=embedding.tenant_id,
                    tool_version_id=embedding.tool_version_id,
                    embedding_model=embedding.embedding_model,
                    embedding_dimensions=embedding.embedding_dimensions,
                    source_digest=embedding.source_digest,
                    vector=embedding.vector,
                    indexed_at=embedding.indexed_at,
                )
            )
            self._store[scope] = persisted


class InMemoryToolSearchUnitOfWork:
    def __init__(
        self,
        store: dict[EmbeddingScope, ToolSearchEmbedding],
        lock: asyncio.Lock,
    ) -> None:
        self._store = store
        self._lock = lock
        self._working: dict[EmbeddingScope, ToolSearchEmbedding] | None = None
        self._embeddings: InMemoryToolSearchEmbeddingRepository | None = None

    @property
    def embeddings(self) -> InMemoryToolSearchEmbeddingRepository:
        if self._embeddings is None:
            raise RuntimeError("unit of work must be entered before accessing repository")
        return self._embeddings

    async def __aenter__(self) -> InMemoryToolSearchUnitOfWork:
        await self._lock.acquire()
        self._working = dict(self._store)
        self._embeddings = InMemoryToolSearchEmbeddingRepository(self._working)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        _ = (exc_type, exc_value, traceback)
        self._working = None
        self._embeddings = None
        self._lock.release()

    async def commit(self) -> None:
        working = self._require_working()
        self._store.clear()
        self._store.update(working)

    async def rollback(self) -> None:
        working = self._require_working()
        working.clear()
        working.update(self._store)

    def _require_working(self) -> dict[EmbeddingScope, ToolSearchEmbedding]:
        if self._working is None:
            raise RuntimeError("unit of work must be entered before transaction control")
        return self._working


class InMemoryToolSearchUnitOfWorkFactory:
    def __init__(self) -> None:
        self._store: dict[EmbeddingScope, ToolSearchEmbedding] = {}
        self._lock = asyncio.Lock()

    def __call__(self) -> InMemoryToolSearchUnitOfWork:
        return InMemoryToolSearchUnitOfWork(self._store, self._lock)

    @property
    def reader(self) -> InMemoryToolSearchEmbeddingRepository:
        return InMemoryToolSearchEmbeddingRepository(self._store)
