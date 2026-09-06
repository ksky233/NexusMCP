"""Toolset Aggregate 的 SQLAlchemy Model。"""

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from nexusmcp.infrastructure.persistence.base import Base, UUIDPrimaryKeyMixin


class ToolsetModel(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "toolset"
    __table_args__ = (
        CheckConstraint("kind IN ('explicit', 'all_published')", name="kind"),
        CheckConstraint(
            "discovery_mode IN ('direct', 'search_first')",
            name="discovery_mode",
        ),
        CheckConstraint("status IN ('draft', 'active', 'disabled')", name="status"),
        CheckConstraint("revision > 0", name="revision_positive"),
        UniqueConstraint("tenant_id", "slug", name="uq_toolset_tenant_slug"),
        Index("ix_toolset_tenant_status", "tenant_id", "status"),
        Index(
            "uq_toolset_all_published_tenant",
            "tenant_id",
            unique=True,
            postgresql_where=text("kind = 'all_published'"),
        ),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenant.id", ondelete="RESTRICT"),
        nullable=False,
    )
    slug: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    discovery_mode: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    membership_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )


class ToolsetMemberModel(Base):
    __tablename__ = "toolset_member"
    __table_args__ = (Index("ix_toolset_member_tenant_tool", "tenant_id", "tool_id"),)

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenant.id", ondelete="RESTRICT"),
        nullable=False,
    )
    toolset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("toolset.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    tool_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tool.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    added_by: Mapped[str] = mapped_column(String(255), nullable=False)
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ToolsetAccessGrantModel(Base):
    __tablename__ = "toolset_access_grant"
    __table_args__ = (
        Index(
            "ix_toolset_access_grant_tenant_principal",
            "tenant_id",
            "principal_id",
        ),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenant.id", ondelete="RESTRICT"),
        nullable=False,
    )
    toolset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("toolset.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    principal_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    granted_by: Mapped[str] = mapped_column(String(255), nullable=False)
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
