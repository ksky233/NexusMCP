"""add tool search reindex job

Revision ID: a7c4e91d2f60
Revises: f6b8d0e32c47
Create Date: 2026-08-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a7c4e91d2f60"
down_revision: str | Sequence[str] | None = "f6b8d0e32c47"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tool_search_reindex_job",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("requested_by", sa.String(length=256), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("force", sa.Boolean(), nullable=False),
        sa.Column("batch_size", sa.Integer(), nullable=False),
        sa.Column("embedding_model", sa.String(length=256), nullable=False),
        sa.Column("embedding_dimensions", sa.Integer(), nullable=False),
        sa.Column("published_count", sa.Integer(), nullable=False),
        sa.Column("current_count", sa.Integer(), nullable=False),
        sa.Column("pending_count", sa.Integer(), nullable=False),
        sa.Column("embedded_count", sa.Integer(), nullable=False),
        sa.Column("batch_count", sa.Integer(), nullable=False),
        sa.Column("error_code", sa.String(length=128), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'succeeded', 'failed')",
            name=op.f("ck_tool_search_reindex_job_status"),
        ),
        sa.CheckConstraint(
            "batch_size BETWEEN 1 AND 64",
            name=op.f("ck_tool_search_reindex_job_batch_size"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f("fk_tool_search_reindex_job_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tool_search_reindex_job")),
    )
    op.create_index(
        "ix_tool_search_reindex_job_tenant_created",
        "tool_search_reindex_job",
        ["tenant_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "uq_tool_search_reindex_job_active_tenant",
        "tool_search_reindex_job",
        ["tenant_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('pending', 'running')"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_tool_search_reindex_job_active_tenant",
        table_name="tool_search_reindex_job",
        postgresql_where=sa.text("status IN ('pending', 'running')"),
    )
    op.drop_index(
        "ix_tool_search_reindex_job_tenant_created",
        table_name="tool_search_reindex_job",
    )
    op.drop_table("tool_search_reindex_job")
