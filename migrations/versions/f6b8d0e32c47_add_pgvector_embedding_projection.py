"""add pgvector embedding projection

Revision ID: f6b8d0e32c47
Revises: e4a7c9d21b35
Create Date: 2026-08-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import VECTOR

revision: str = "f6b8d0e32c47"
down_revision: str | Sequence[str] | None = "e4a7c9d21b35"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

EMBEDDING_DIMENSIONS = 2048


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "tool_search_embedding",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("tool_version_id", sa.Uuid(), nullable=False),
        sa.Column("embedding_model", sa.String(length=256), nullable=False),
        sa.Column("embedding_dimensions", sa.Integer(), nullable=False),
        sa.Column("source_digest", sa.String(length=64), nullable=False),
        sa.Column("embedding", VECTOR(dim=EMBEDDING_DIMENSIONS), nullable=False),
        sa.Column("indexed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            f"embedding_dimensions = {EMBEDDING_DIMENSIONS}",
            name=op.f("ck_tool_search_embedding_dimensions"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f("fk_tool_search_embedding_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tool_version_id"],
            ["tool_version.id"],
            name=op.f("fk_tool_search_embedding_tool_version_id_tool_version"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tool_search_embedding")),
        sa.UniqueConstraint(
            "tenant_id",
            "tool_version_id",
            "embedding_model",
            "embedding_dimensions",
            name="uq_tool_search_embedding_scope",
        ),
    )
    op.create_index(
        "ix_tool_search_embedding_source_digest",
        "tool_search_embedding",
        ["source_digest"],
        unique=False,
    )
    op.create_index(
        "ix_tool_search_embedding_tenant_model",
        "tool_search_embedding",
        ["tenant_id", "embedding_model"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_tool_search_embedding_tenant_model",
        table_name="tool_search_embedding",
    )
    op.drop_index(
        "ix_tool_search_embedding_source_digest",
        table_name="tool_search_embedding",
    )
    op.drop_table("tool_search_embedding")
    # vector Extension 属于数据库基础设施，避免 CASCADE 删除其他 Projection。
