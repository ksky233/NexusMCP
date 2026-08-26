"""add retry and idempotency

Revision ID: e4a7c9d21b35
Revises: d7e2b4c91a60
Create Date: 2026-08-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e4a7c9d21b35"
down_revision: str | Sequence[str] | None = "d7e2b4c91a60"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "approval_request",
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "tool_execution",
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
    )
    op.create_index(
        "uq_tool_execution_idempotency_scope",
        "tool_execution",
        ["tenant_id", "principal_id", "tool_version_id", "idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )
    op.create_table(
        "execution_attempt",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("execution_id", sa.Uuid(), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(length=128), nullable=True),
        sa.Column("error_category", sa.String(length=32), nullable=True),
        sa.Column("upstream_status", sa.Integer(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "status IN ('running', 'succeeded', 'failed', 'unknown', 'cancelled')",
            name=op.f("ck_execution_attempt_status"),
        ),
        sa.CheckConstraint(
            "attempt_number > 0",
            name=op.f("ck_execution_attempt_attempt_number_positive"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f("fk_execution_attempt_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["execution_id"],
            ["tool_execution.id"],
            name=op.f("fk_execution_attempt_execution_id_tool_execution"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_execution_attempt")),
    )
    op.create_index(
        "ix_execution_attempt_tenant_execution",
        "execution_attempt",
        ["tenant_id", "execution_id"],
        unique=False,
    )
    op.create_index(
        "uq_execution_attempt_execution_number",
        "execution_attempt",
        ["execution_id", "attempt_number"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        "uq_execution_attempt_execution_number",
        table_name="execution_attempt",
    )
    op.drop_index(
        "ix_execution_attempt_tenant_execution",
        table_name="execution_attempt",
    )
    op.drop_table("execution_attempt")
    op.drop_index(
        "uq_tool_execution_idempotency_scope",
        table_name="tool_execution",
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )
    op.drop_column("tool_execution", "attempt_count")
    op.drop_column("approval_request", "idempotency_key")
