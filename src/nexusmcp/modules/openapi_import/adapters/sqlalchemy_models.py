"""OpenAPI Import 上下文的 SQLAlchemy Model。"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from nexusmcp.infrastructure.persistence.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class OpenApiImportJobModel(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "openapi_import_job"
    __table_args__ = (
        CheckConstraint("source_type IN ('upload', 'local_fixture', 'url')", name="source_type"),
        CheckConstraint(
            "status IN ('pending', 'validating', 'parsing', 'completed', 'failed')",
            name="status",
        ),
        Index(
            "ix_openapi_import_job_tenant_digest_created",
            "tenant_id",
            "source_digest",
            "created_at",
        ),
        Index("ix_openapi_import_job_upstream_status", "upstream_service_id", "status"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenant.id", ondelete="RESTRICT"),
        nullable=False,
    )
    upstream_service_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("upstream_service.id", ondelete="RESTRICT"),
        nullable=False,
    )
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_ref: Mapped[str] = mapped_column(String(2048), nullable=False)
    source_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    openapi_version: Mapped[str | None] = mapped_column(String(16))
    operation_allowlist_json: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )
    allowlist_snapshot_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="pending",
        server_default="pending",
    )
    error_summary: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ImportedOperationModel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "imported_operation"
    __table_args__ = (
        UniqueConstraint(
            "import_job_id",
            "operation_key",
            name="uq_imported_operation_job_operation",
        ),
        CheckConstraint(
            "review_status IN ('pending', 'accepted', 'rejected', 'needs_change')",
            name="review_status",
        ),
        CheckConstraint(
            "conflict_status IN ('none', 'name_collision', 'missing_operation_id', 'unsupported')",
            name="conflict_status",
        ),
        Index("ix_imported_operation_tenant_review", "tenant_id", "review_status"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenant.id", ondelete="RESTRICT"),
        nullable=False,
    )
    import_job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("openapi_import_job.id", ondelete="RESTRICT"),
        nullable=False,
    )
    upstream_service_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("upstream_service.id", ondelete="RESTRICT"),
        nullable=False,
    )
    operation_key: Mapped[str] = mapped_column(String(512), nullable=False)
    operation_id: Mapped[str | None] = mapped_column(String(256))
    method: Mapped[str] = mapped_column(String(16), nullable=False)
    path: Mapped[str] = mapped_column(String(1024), nullable=False)
    normalized_operation_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    generated_tool_name: Mapped[str | None] = mapped_column(String(256))
    conflict_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="none",
        server_default="none",
    )
    review_status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="pending",
        server_default="pending",
    )
    review_notes: Mapped[str | None] = mapped_column(Text)
    draft_tool_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("tool_version.id", ondelete="SET NULL"),
    )
    draft_tool_binding_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(
            "tool_binding.id",
            name="fk_imported_operation_draft_tool_binding_id_tool_binding",
            ondelete="SET NULL",
            use_alter=True,
        ),
    )
