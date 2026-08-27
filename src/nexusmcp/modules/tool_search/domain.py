"""Tool Search Document、Embedding Vector 与 Projection Domain。"""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from math import isfinite

from nexusmcp.modules.catalog.domain import PublishedToolSearchHit


class ToolRetrievalMode(StrEnum):
    LEXICAL = "lexical"
    HYBRID = "hybrid"


@dataclass(frozen=True, slots=True)
class ToolSearchDocument:
    tenant_id: str
    tool_id: str
    tool_version_id: str
    canonical_name: str
    content: str
    source_digest: str

    def __post_init__(self) -> None:
        for field_name, value in (
            ("tenant id", self.tenant_id),
            ("tool id", self.tool_id),
            ("tool version id", self.tool_version_id),
            ("canonical name", self.canonical_name),
            ("tool search document", self.content),
        ):
            if not value.strip():
                raise ValueError(f"{field_name} must not be blank")
        if len(self.source_digest) != 64:
            raise ValueError("tool search source digest must be a SHA-256 hex digest")


@dataclass(frozen=True, slots=True)
class EmbeddingVector:
    model: str
    dimensions: int
    values: tuple[float, ...]

    def __post_init__(self) -> None:
        if not self.model.strip():
            raise ValueError("embedding model must not be blank")
        if self.dimensions <= 0 or len(self.values) != self.dimensions:
            raise ValueError("embedding vector dimensions did not match values")
        if not all(isfinite(value) for value in self.values):
            raise ValueError("embedding vector values must be finite")


@dataclass(frozen=True, slots=True)
class ToolSearchEmbedding:
    id: str
    tenant_id: str
    tool_version_id: str
    embedding_model: str
    embedding_dimensions: int
    source_digest: str
    vector: EmbeddingVector
    indexed_at: datetime

    def __post_init__(self) -> None:
        for field_name, value in (
            ("embedding id", self.id),
            ("tenant id", self.tenant_id),
            ("tool version id", self.tool_version_id),
            ("embedding model", self.embedding_model),
        ):
            if not value.strip():
                raise ValueError(f"{field_name} must not be blank")
        if len(self.source_digest) != 64:
            raise ValueError("embedding source digest must be a SHA-256 hex digest")
        if self.vector.model != self.embedding_model:
            raise ValueError("embedding vector model did not match projection")
        if self.vector.dimensions != self.embedding_dimensions:
            raise ValueError("embedding vector dimensions did not match projection")


@dataclass(frozen=True, slots=True)
class VectorSearchResult:
    """Exact Vector Search 的候选与当前 Scope 索引覆盖情况。"""

    hits: tuple[PublishedToolSearchHit, ...]
    eligible_count: int
    indexed_count: int

    def __post_init__(self) -> None:
        if self.eligible_count < 0 or self.indexed_count < 0:
            raise ValueError("vector search coverage counts must not be negative")
        if self.indexed_count > self.eligible_count:
            raise ValueError("indexed tool count must not exceed eligible tool count")
        if len(self.hits) > self.indexed_count:
            raise ValueError("vector search hits must not exceed indexed tool count")
