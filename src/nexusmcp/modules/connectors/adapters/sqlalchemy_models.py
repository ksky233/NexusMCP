"""Connectors 上下文的 SQLAlchemy Model。"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from nexusmcp.infrastructure.persistence.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class ToolBindingModel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "tool_binding"
    __table_args__ = (
        CheckConstraint("binding_type IN ('http', 'remote_mcp')", name="binding_type"),
        CheckConstraint("status IN ('draft', 'published', 'disabled')", name="status"),
        UniqueConstraint(
            "tool_version_id",
            name="uq_tool_binding_tool_version",
        ),
        Index("ix_tool_binding_tenant_status", "tenant_id", "status"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenant.id", ondelete="RESTRICT"),
        nullable=False,
    )
    tool_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tool_version.id", ondelete="RESTRICT"),
        nullable=False,
    )
    upstream_service_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("upstream_service.id", ondelete="RESTRICT"),
        nullable=False,
    )
    imported_operation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("imported_operation.id", ondelete="SET NULL"),
    )
    binding_type: Mapped[str] = mapped_column(String(32), nullable=False)
    binding_config_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    binding_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="draft",
        server_default="draft",
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
