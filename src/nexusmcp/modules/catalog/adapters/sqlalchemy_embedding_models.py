"""Tool Semantic Search 的可重建 pgvector Projection Model。"""

import uuid
from datetime import datetime

from pgvector.sqlalchemy import VECTOR
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from nexusmcp.infrastructure.persistence.base import Base, UUIDPrimaryKeyMixin

TOOL_EMBEDDING_DIMENSIONS = 2048


class ToolSearchEmbeddingModel(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "tool_search_embedding"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "tool_version_id",
            "embedding_model",
            "embedding_dimensions",
            name="uq_tool_search_embedding_scope",
        ),
        CheckConstraint(
            f"embedding_dimensions = {TOOL_EMBEDDING_DIMENSIONS}",
            name="dimensions",
        ),
        Index(
            "ix_tool_search_embedding_tenant_model",
            "tenant_id",
            "embedding_model",
        ),
        Index("ix_tool_search_embedding_source_digest", "source_digest"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenant.id", ondelete="RESTRICT"),
        nullable=False,
    )
    tool_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tool_version.id", ondelete="RESTRICT"),
        nullable=False,
    )
    embedding_model: Mapped[str] = mapped_column(String(256), nullable=False)
    embedding_dimensions: Mapped[int] = mapped_column(Integer, nullable=False)
    source_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    embedding: Mapped[list[float]] = mapped_column(
        VECTOR(TOOL_EMBEDDING_DIMENSIONS),
        nullable=False,
    )
    indexed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
