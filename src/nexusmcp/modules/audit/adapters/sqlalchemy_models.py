"""Audit 上下文的 SQLAlchemy Model。"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from nexusmcp.infrastructure.persistence.base import Base, UUIDPrimaryKeyMixin


class AuditEventModel(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "audit_event"
    __table_args__ = (
        CheckConstraint(
            "action IN ('tool_call', 'approval_decision', 'credential_resolution')",
            name="action",
        ),
        CheckConstraint(
            "outcome IN ('allowed', 'denied', 'approval_required', 'succeeded', "
            "'failed', 'unknown', 'cancelled')",
            name="outcome",
        ),
        Index("ix_audit_event_tenant_occurred", "tenant_id", "occurred_at"),
        Index("ix_audit_event_tenant_execution", "tenant_id", "execution_id"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenant.id", ondelete="RESTRICT"),
        nullable=False,
    )
    actor_id: Mapped[str] = mapped_column(String(255), nullable=False)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_id: Mapped[str] = mapped_column(String(255), nullable=False)
    outcome: Mapped[str] = mapped_column(String(32), nullable=False)
    request_id: Mapped[str] = mapped_column(String(128), nullable=False)
    trace_id: Mapped[str] = mapped_column(String(64), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    arguments_digest: Mapped[str | None] = mapped_column(String(64))
    policy_version: Mapped[str | None] = mapped_column(String(128))
    reason_code: Mapped[str | None] = mapped_column(String(128))
    execution_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("tool_execution.id", ondelete="RESTRICT")
    )
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
