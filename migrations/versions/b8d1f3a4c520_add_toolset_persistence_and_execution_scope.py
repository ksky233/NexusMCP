"""add toolset persistence and execution scope

Revision ID: b8d1f3a4c520
Revises: a7c4e91d2f60
Create Date: 2026-09-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b8d1f3a4c520"
down_revision: str | Sequence[str] | None = "a7c4e91d2f60"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "toolset",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("discovery_mode", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("revision", sa.Integer(), server_default="1", nullable=False),
        sa.Column("membership_digest", sa.String(length=64), nullable=False),
        sa.Column("created_by", sa.String(length=255), nullable=False),
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
            "kind IN ('explicit', 'all_published')",
            name=op.f("ck_toolset_kind"),
        ),
        sa.CheckConstraint(
            "discovery_mode IN ('direct', 'search_first')",
            name=op.f("ck_toolset_discovery_mode"),
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'active', 'disabled')",
            name=op.f("ck_toolset_status"),
        ),
        sa.CheckConstraint("revision > 0", name=op.f("ck_toolset_revision_positive")),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f("fk_toolset_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_toolset")),
        sa.UniqueConstraint(
            "tenant_id",
            "slug",
            name=op.f("uq_toolset_tenant_slug"),
        ),
    )
    op.create_index(
        "ix_toolset_tenant_status",
        "toolset",
        ["tenant_id", "status"],
        unique=False,
    )
    op.create_index(
        "uq_toolset_all_published_tenant",
        "toolset",
        ["tenant_id"],
        unique=True,
        postgresql_where=sa.text("kind = 'all_published'"),
    )
    op.create_table(
        "toolset_member",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("toolset_id", sa.Uuid(), nullable=False),
        sa.Column("tool_id", sa.Uuid(), nullable=False),
        sa.Column("added_by", sa.String(length=255), nullable=False),
        sa.Column("added_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f("fk_toolset_member_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["toolset_id"],
            ["toolset.id"],
            name=op.f("fk_toolset_member_toolset_id_toolset"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tool_id"],
            ["tool.id"],
            name=op.f("fk_toolset_member_tool_id_tool"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "toolset_id",
            "tool_id",
            name=op.f("pk_toolset_member"),
        ),
    )
    op.create_index(
        "ix_toolset_member_tenant_tool",
        "toolset_member",
        ["tenant_id", "tool_id"],
        unique=False,
    )
    op.create_table(
        "toolset_access_grant",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("toolset_id", sa.Uuid(), nullable=False),
        sa.Column("principal_id", sa.String(length=255), nullable=False),
        sa.Column("granted_by", sa.String(length=255), nullable=False),
        sa.Column("granted_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f("fk_toolset_access_grant_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["toolset_id"],
            ["toolset.id"],
            name=op.f("fk_toolset_access_grant_toolset_id_toolset"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "toolset_id",
            "principal_id",
            name=op.f("pk_toolset_access_grant"),
        ),
    )
    op.create_index(
        "ix_toolset_access_grant_tenant_principal",
        "toolset_access_grant",
        ["tenant_id", "principal_id"],
        unique=False,
    )
    op.add_column(
        "tool_execution",
        sa.Column("mcp_scope_type", sa.String(length=16), server_default="root", nullable=False),
    )
    op.add_column(
        "tool_execution",
        sa.Column("toolset_id", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "tool_execution",
        sa.Column("toolset_revision", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        op.f("fk_tool_execution_toolset_id_toolset"),
        "tool_execution",
        "toolset",
        ["toolset_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_check_constraint(
        op.f("ck_tool_execution_mcp_scope"),
        "tool_execution",
        "(mcp_scope_type = 'root' AND toolset_id IS NULL AND toolset_revision IS NULL) OR "
        "(mcp_scope_type = 'toolset' AND toolset_id IS NOT NULL AND toolset_revision > 0)",
    )
    op.create_index(
        "ix_tool_execution_tenant_toolset",
        "tool_execution",
        ["tenant_id", "toolset_id", "planned_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_tool_execution_tenant_toolset", table_name="tool_execution")
    op.drop_constraint(
        op.f("ck_tool_execution_mcp_scope"),
        "tool_execution",
        type_="check",
    )
    op.drop_constraint(
        op.f("fk_tool_execution_toolset_id_toolset"),
        "tool_execution",
        type_="foreignkey",
    )
    op.drop_column("tool_execution", "toolset_revision")
    op.drop_column("tool_execution", "toolset_id")
    op.drop_column("tool_execution", "mcp_scope_type")
    op.drop_index(
        "ix_toolset_access_grant_tenant_principal",
        table_name="toolset_access_grant",
    )
    op.drop_table("toolset_access_grant")
    op.drop_index("ix_toolset_member_tenant_tool", table_name="toolset_member")
    op.drop_table("toolset_member")
    op.drop_index(
        "uq_toolset_all_published_tenant",
        table_name="toolset",
        postgresql_where=sa.text("kind = 'all_published'"),
    )
    op.drop_index("ix_toolset_tenant_status", table_name="toolset")
    op.drop_table("toolset")
