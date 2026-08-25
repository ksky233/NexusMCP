"""Registry 上下文的 SQLAlchemy Model。"""

import uuid
from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from nexusmcp.infrastructure.persistence.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class UpstreamServiceModel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "upstream_service"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "namespace",
            "name",
            name="uq_upstream_service_tenant_namespace_name",
        ),
        CheckConstraint("service_type IN ('http', 'remote_mcp')", name="service_type"),
        CheckConstraint("status IN ('draft', 'active', 'disabled')", name="status"),
        Index("ix_upstream_service_tenant_status", "tenant_id", "status"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenant.id", ondelete="RESTRICT"),
        nullable=False,
    )
    namespace: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    owner: Mapped[str] = mapped_column(String(128), nullable=False)
    service_type: Mapped[str] = mapped_column(String(32), nullable=False)
    transport_type: Mapped[str] = mapped_column(String(32), nullable=False)
    endpoint: Mapped[str] = mapped_column(String(2048), nullable=False)
    protocol_min: Mapped[str | None] = mapped_column(String(16))
    protocol_max: Mapped[str | None] = mapped_column(String(16))
    auth_scheme: Mapped[str | None] = mapped_column(String(32))
    config_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="draft",
        server_default="draft",
    )
