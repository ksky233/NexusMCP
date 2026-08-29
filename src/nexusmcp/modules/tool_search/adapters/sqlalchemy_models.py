"""Tool Semantic Search 的可重建 pgvector Projection Model。"""

import uuid
from datetime import datetime

from pgvector.sqlalchemy import VECTOR
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from nexusmcp.infrastructure.persistence.base import (
    Base,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)

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


class ToolSearchReindexJobModel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "tool_search_reindex_job"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'running', 'succeeded', 'failed')",
            name="status",
        ),
        CheckConstraint("batch_size BETWEEN 1 AND 64", name="batch_size"),
        Index(
            "uq_tool_search_reindex_job_active_tenant",
            "tenant_id",
            unique=True,
            postgresql_where=text("status IN ('pending', 'running')"),
        ),
        Index(
            "ix_tool_search_reindex_job_tenant_created",
            "tenant_id",
            "created_at",
        ),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenant.id", ondelete="RESTRICT"),
        nullable=False,
    )
    requested_by: Mapped[str] = mapped_column(String(256), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    force: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    batch_size: Mapped[int] = mapped_column(Integer, nullable=False)
    embedding_model: Mapped[str] = mapped_column(String(256), nullable=False)
    embedding_dimensions: Mapped[int] = mapped_column(Integer, nullable=False)
    published_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    current_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    pending_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    embedded_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    batch_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_code: Mapped[str | None] = mapped_column(String(128))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
