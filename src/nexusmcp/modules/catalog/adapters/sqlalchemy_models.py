"""Tool Catalog 上下文的 SQLAlchemy Model。"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    Computed,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from nexusmcp.infrastructure.persistence.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class ToolModel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "tool"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "canonical_name",
            name="uq_tool_tenant_canonical_name",
        ),
        CheckConstraint("status IN ('active', 'disabled')", name="status"),
        Index("ix_tool_tenant_namespace", "tenant_id", "namespace"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenant.id", ondelete="RESTRICT"),
        nullable=False,
    )
    namespace: Mapped[str] = mapped_column(String(64), nullable=False)
    canonical_name: Mapped[str] = mapped_column(String(256), nullable=False)
    owner: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="active",
        server_default="active",
    )


class ToolVersionModel(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "tool_version"
    __table_args__ = (
        UniqueConstraint("tool_id", "version", name="uq_tool_version_tool_version"),
        CheckConstraint(
            "side_effect IN ('read_only', 'idempotent_write', 'non_idempotent_write', 'unknown')",
            name="side_effect",
        ),
        CheckConstraint(
            "visibility IN ('public', 'authenticated', 'restricted')",
            name="visibility",
        ),
        CheckConstraint(
            "status IN ('draft', 'review', 'published', 'retired')",
            name="status",
        ),
        Index(
            "uq_tool_version_one_published",
            "tool_id",
            unique=True,
            postgresql_where=text("status = 'published'"),
        ),
        Index("ix_tool_version_schema_digest", "schema_digest"),
        Index("ix_tool_version_tenant_status", "tenant_id", "status"),
        Index(
            "ix_tool_version_search_vector_gin",
            "search_vector",
            postgresql_using="gin",
        ),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenant.id", ondelete="RESTRICT"),
        nullable=False,
    )
    tool_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tool.id", ondelete="RESTRICT"),
        nullable=False,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    display_name: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    input_schema_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    output_schema_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    schema_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    tags_json: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )
    search_name: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
        server_default="",
    )
    search_tags: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
        server_default="",
    )
    search_description: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
        server_default="",
    )
    search_vector: Mapped[Any] = mapped_column(
        TSVECTOR,
        Computed(
            "setweight(to_tsvector('simple'::regconfig, COALESCE(search_name, '')), 'A') || "
            "setweight(to_tsvector('simple'::regconfig, COALESCE(search_tags, '')), 'B') || "
            "setweight(to_tsvector('simple'::regconfig, COALESCE(search_description, '')), 'C')",
            persisted=True,
        ),
    )
    side_effect: Mapped[str] = mapped_column(String(32), nullable=False)
    visibility: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="draft",
        server_default="draft",
    )
    created_by: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
