"""Embedding Provider、Projection Repository 与 Tool Search UoW Port。"""

from types import TracebackType
from typing import Protocol, Self

from nexusmcp.modules.catalog.domain import ToolSideEffect, ToolVisibility
from nexusmcp.modules.tool_search.domain import (
    EmbeddingVector,
    ToolSearchEmbedding,
    VectorSearchResult,
)


class EmbeddingProvider(Protocol):
    @property
    def model(self) -> str: ...

    @property
    def dimensions(self) -> int: ...

    async def embed(self, texts: tuple[str, ...]) -> tuple[EmbeddingVector, ...]: ...


class VectorToolSearch(Protocol):
    """按 Query Vector 读取可见 Published Tool 的只读 Data Plane Port。"""

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
    ) -> VectorSearchResult: ...


class ToolSearchEmbeddingRepository(Protocol):
    async def list_by_tool_versions(
        self,
        tenant_id: str,
        tool_version_ids: tuple[str, ...],
        *,
        embedding_model: str,
        embedding_dimensions: int,
    ) -> tuple[ToolSearchEmbedding, ...]: ...

    async def upsert_many(
        self,
        tenant_id: str,
        embeddings: tuple[ToolSearchEmbedding, ...],
    ) -> None: ...


class ToolSearchUnitOfWork(Protocol):
    @property
    def embeddings(self) -> ToolSearchEmbeddingRepository: ...

    async def __aenter__(self) -> Self: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...


class ToolSearchUnitOfWorkFactory(Protocol):
    def __call__(self) -> ToolSearchUnitOfWork: ...
