"""add execution and audit

Revision ID: d7e2b4c91a60
Revises: c1f8a3d42e90
Create Date: 2026-08-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "d7e2b4c91a60"
down_revision: str | Sequence[str] | None = "c1f8a3d42e90"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tool_execution",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("request_id", sa.String(length=128), nullable=False),
        sa.Column("trace_id", sa.String(length=64), nullable=False),
        sa.Column("principal_id", sa.String(length=255), nullable=False),
        sa.Column("tool_id", sa.Uuid(), nullable=False),
        sa.Column("tool_version_id", sa.Uuid(), nullable=False),
        sa.Column("tool_binding_id", sa.Uuid(), nullable=False),
        sa.Column("approval_id", sa.Uuid(), nullable=True),
        sa.Column("credential_binding_id", sa.String(length=255), nullable=True),
        sa.Column("arguments_digest", sa.String(length=64), nullable=False),
        sa.Column("policy_version", sa.String(length=128), nullable=False),
        sa.Column("policy_reason_code", sa.String(length=128), nullable=False),
        sa.Column("side_effect", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=True),
        sa.Column("planned_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(length=128), nullable=True),
        sa.Column("error_category", sa.String(length=32), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "status IN ('planned', 'running', 'succeeded', 'failed', 'unknown', 'cancelled')",
            name=op.f("ck_tool_execution_status"),
        ),
        sa.CheckConstraint(
            "side_effect IN ('read_only', 'idempotent_write', 'non_idempotent_write', 'unknown')",
            name=op.f("ck_tool_execution_side_effect"),
        ),
        sa.CheckConstraint(
            "error_category IS NULL OR error_category IN ("
            "'validation', 'authentication', 'authorization', 'approval', 'credential', "
            "'timeout_before_send', 'timeout_after_send', 'network', 'upstream_4xx', "
            "'upstream_5xx', 'cancelled', 'unknown')",
            name=op.f("ck_tool_execution_error_category"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f("fk_tool_execution_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tool_id"],
            ["tool.id"],
            name=op.f("fk_tool_execution_tool_id_tool"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tool_version_id"],
            ["tool_version.id"],
            name=op.f("fk_tool_execution_tool_version_id_tool_version"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tool_binding_id"],
            ["tool_binding.id"],
            name=op.f("fk_tool_execution_tool_binding_id_tool_binding"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["approval_id"],
            ["approval_request.id"],
            name=op.f("fk_tool_execution_approval_id_approval_request"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tool_execution")),
    )
    op.create_index(
        "ix_tool_execution_tenant_status_planned",
        "tool_execution",
        ["tenant_id", "status", "planned_at"],
        unique=False,
    )
    op.create_index(
        "ix_tool_execution_tenant_request",
        "tool_execution",
        ["tenant_id", "request_id"],
        unique=False,
    )
    op.create_index(
        "ix_tool_execution_tenant_trace",
        "tool_execution",
        ["tenant_id", "trace_id"],
        unique=False,
    )
    op.create_table(
        "audit_event",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("actor_id", sa.String(length=255), nullable=False),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("resource_type", sa.String(length=64), nullable=False),
        sa.Column("resource_id", sa.String(length=255), nullable=False),
        sa.Column("outcome", sa.String(length=32), nullable=False),
        sa.Column("request_id", sa.String(length=128), nullable=False),
        sa.Column("trace_id", sa.String(length=64), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("arguments_digest", sa.String(length=64), nullable=True),
        sa.Column("policy_version", sa.String(length=128), nullable=True),
        sa.Column("reason_code", sa.String(length=128), nullable=True),
        sa.Column("execution_id", sa.Uuid(), nullable=True),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "action IN ('tool_call', 'approval_decision', 'credential_resolution')",
            name=op.f("ck_audit_event_action"),
        ),
        sa.CheckConstraint(
            "outcome IN ('allowed', 'denied', 'approval_required', 'succeeded', "
            "'failed', 'unknown', 'cancelled')",
            name=op.f("ck_audit_event_outcome"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f("fk_audit_event_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["execution_id"],
            ["tool_execution.id"],
            name=op.f("fk_audit_event_execution_id_tool_execution"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_event")),
    )
    op.create_index(
        "ix_audit_event_tenant_occurred",
        "audit_event",
        ["tenant_id", "occurred_at"],
        unique=False,
    )
    op.create_index(
        "ix_audit_event_tenant_execution",
        "audit_event",
        ["tenant_id", "execution_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_audit_event_tenant_execution", table_name="audit_event")
    op.drop_index("ix_audit_event_tenant_occurred", table_name="audit_event")
    op.drop_table("audit_event")
    op.drop_index("ix_tool_execution_tenant_trace", table_name="tool_execution")
    op.drop_index("ix_tool_execution_tenant_request", table_name="tool_execution")
    op.drop_index("ix_tool_execution_tenant_status_planned", table_name="tool_execution")
    op.drop_table("tool_execution")
