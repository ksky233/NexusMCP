"""Execution 上下文的 SQLAlchemy Model。"""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from nexusmcp.infrastructure.persistence.base import Base, UUIDPrimaryKeyMixin


class ToolExecutionModel(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "tool_execution"
    __table_args__ = (
        CheckConstraint(
            "status IN ('planned', 'running', 'succeeded', 'failed', 'unknown', 'cancelled')",
            name="status",
        ),
        CheckConstraint(
            "side_effect IN ('read_only', 'idempotent_write', 'non_idempotent_write', 'unknown')",
            name="side_effect",
        ),
        CheckConstraint(
            "error_category IS NULL OR error_category IN ("
            "'validation', 'authentication', 'authorization', 'approval', 'credential', "
            "'timeout_before_send', 'timeout_after_send', 'network', 'upstream_4xx', "
            "'upstream_5xx', 'cancelled', 'unknown')",
            name="error_category",
        ),
        Index("ix_tool_execution_tenant_status_planned", "tenant_id", "status", "planned_at"),
        Index("ix_tool_execution_tenant_request", "tenant_id", "request_id"),
        Index("ix_tool_execution_tenant_trace", "tenant_id", "trace_id"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenant.id", ondelete="RESTRICT"),
        nullable=False,
    )
    request_id: Mapped[str] = mapped_column(String(128), nullable=False)
    trace_id: Mapped[str] = mapped_column(String(64), nullable=False)
    principal_id: Mapped[str] = mapped_column(String(255), nullable=False)
    tool_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tool.id", ondelete="RESTRICT"),
        nullable=False,
    )
    tool_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tool_version.id", ondelete="RESTRICT"),
        nullable=False,
    )
    tool_binding_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tool_binding.id", ondelete="RESTRICT"),
        nullable=False,
    )
    approval_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("approval_request.id", ondelete="RESTRICT")
    )
    credential_binding_id: Mapped[str | None] = mapped_column(String(255))
    arguments_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    policy_version: Mapped[str] = mapped_column(String(128), nullable=False)
    policy_reason_code: Mapped[str] = mapped_column(String(128), nullable=False)
    side_effect: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(String(255))
    planned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(128))
    error_category: Mapped[str | None] = mapped_column(String(32))
