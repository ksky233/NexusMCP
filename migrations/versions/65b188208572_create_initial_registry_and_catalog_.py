"""Create initial Registry and Catalog schema

Revision ID: 65b188208572
Revises:
Create Date: 2026-08-25 15:58:36.984548
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "65b188208572"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """应用初始 Schema。"""
    op.create_table(
        "tenant",
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="active", nullable=False),
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
        sa.CheckConstraint("status IN ('active', 'disabled')", name=op.f("ck_tenant_status")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tenant")),
    )
    op.create_table(
        "tool",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("namespace", sa.String(length=64), nullable=False),
        sa.Column("canonical_name", sa.String(length=256), nullable=False),
        sa.Column("owner", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="active", nullable=False),
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
        sa.CheckConstraint("status IN ('active', 'disabled')", name=op.f("ck_tool_status")),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenant.id"], name=op.f("fk_tool_tenant_id_tenant"), ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tool")),
        sa.UniqueConstraint("tenant_id", "canonical_name", name="uq_tool_tenant_canonical_name"),
    )
    op.create_index("ix_tool_tenant_namespace", "tool", ["tenant_id", "namespace"], unique=False)
    op.create_table(
        "upstream_service",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("namespace", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("owner", sa.String(length=128), nullable=False),
        sa.Column("service_type", sa.String(length=32), nullable=False),
        sa.Column("transport_type", sa.String(length=32), nullable=False),
        sa.Column("endpoint", sa.String(length=2048), nullable=False),
        sa.Column("protocol_min", sa.String(length=16), nullable=True),
        sa.Column("protocol_max", sa.String(length=16), nullable=True),
        sa.Column("auth_scheme", sa.String(length=32), nullable=True),
        sa.Column(
            "config_json",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=16), server_default="draft", nullable=False),
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
            "service_type IN ('http', 'remote_mcp')", name=op.f("ck_upstream_service_service_type")
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'active', 'disabled')", name=op.f("ck_upstream_service_status")
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f("fk_upstream_service_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_upstream_service")),
        sa.UniqueConstraint(
            "tenant_id", "namespace", "name", name="uq_upstream_service_tenant_namespace_name"
        ),
    )
    op.create_index(
        "ix_upstream_service_tenant_status",
        "upstream_service",
        ["tenant_id", "status"],
        unique=False,
    )
    op.create_table(
        "openapi_import_job",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("upstream_service_id", sa.Uuid(), nullable=False),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("source_ref", sa.String(length=2048), nullable=False),
        sa.Column("source_digest", sa.String(length=64), nullable=False),
        sa.Column("openapi_version", sa.String(length=16), nullable=True),
        sa.Column(
            "operation_allowlist_json",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "allowlist_snapshot_json",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=16), server_default="pending", nullable=False),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(length=128), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "source_type IN ('upload', 'local_fixture', 'url')",
            name=op.f("ck_openapi_import_job_source_type"),
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'validating', 'parsing', 'completed', 'failed')",
            name=op.f("ck_openapi_import_job_status"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f("fk_openapi_import_job_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["upstream_service_id"],
            ["upstream_service.id"],
            name=op.f("fk_openapi_import_job_upstream_service_id_upstream_service"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_openapi_import_job")),
    )
    op.create_index(
        "ix_openapi_import_job_tenant_digest_created",
        "openapi_import_job",
        ["tenant_id", "source_digest", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_openapi_import_job_upstream_status",
        "openapi_import_job",
        ["upstream_service_id", "status"],
        unique=False,
    )
    op.create_table(
        "tool_version",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("tool_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("display_name", sa.String(length=256), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("input_schema_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("output_schema_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("schema_digest", sa.String(length=64), nullable=False),
        sa.Column(
            "tags_json",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("side_effect", sa.String(length=32), nullable=False),
        sa.Column("visibility", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="draft", nullable=False),
        sa.Column("created_by", sa.String(length=128), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "side_effect IN ('read_only', 'idempotent_write', 'non_idempotent_write', 'unknown')",
            name=op.f("ck_tool_version_side_effect"),
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'review', 'published', 'retired')",
            name=op.f("ck_tool_version_status"),
        ),
        sa.CheckConstraint(
            "visibility IN ('public', 'authenticated', 'restricted')",
            name=op.f("ck_tool_version_visibility"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f("fk_tool_version_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tool_id"], ["tool.id"], name=op.f("fk_tool_version_tool_id_tool"), ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tool_version")),
        sa.UniqueConstraint("tool_id", "version", name="uq_tool_version_tool_version"),
    )
    op.create_index(
        "ix_tool_version_schema_digest", "tool_version", ["schema_digest"], unique=False
    )
    op.create_index(
        "ix_tool_version_tenant_status", "tool_version", ["tenant_id", "status"], unique=False
    )
    op.create_index(
        "uq_tool_version_one_published",
        "tool_version",
        ["tool_id"],
        unique=True,
        postgresql_where=sa.text("status = 'published'"),
    )
    op.create_table(
        "imported_operation",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("import_job_id", sa.Uuid(), nullable=False),
        sa.Column("upstream_service_id", sa.Uuid(), nullable=False),
        sa.Column("operation_key", sa.String(length=512), nullable=False),
        sa.Column("operation_id", sa.String(length=256), nullable=True),
        sa.Column("method", sa.String(length=16), nullable=False),
        sa.Column("path", sa.String(length=1024), nullable=False),
        sa.Column(
            "normalized_operation_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column("generated_tool_name", sa.String(length=256), nullable=True),
        sa.Column("conflict_status", sa.String(length=32), server_default="none", nullable=False),
        sa.Column("review_status", sa.String(length=16), server_default="pending", nullable=False),
        sa.Column("review_notes", sa.Text(), nullable=True),
        sa.Column("draft_tool_version_id", sa.Uuid(), nullable=True),
        sa.Column("draft_tool_binding_id", sa.Uuid(), nullable=True),
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
            "conflict_status IN ('none', 'name_collision', 'missing_operation_id', 'unsupported')",
            name=op.f("ck_imported_operation_conflict_status"),
        ),
        sa.CheckConstraint(
            "review_status IN ('pending', 'accepted', 'rejected', 'needs_change')",
            name=op.f("ck_imported_operation_review_status"),
        ),
        sa.ForeignKeyConstraint(
            ["draft_tool_version_id"],
            ["tool_version.id"],
            name=op.f("fk_imported_operation_draft_tool_version_id_tool_version"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["import_job_id"],
            ["openapi_import_job.id"],
            name=op.f("fk_imported_operation_import_job_id_openapi_import_job"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f("fk_imported_operation_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["upstream_service_id"],
            ["upstream_service.id"],
            name=op.f("fk_imported_operation_upstream_service_id_upstream_service"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_imported_operation")),
        sa.UniqueConstraint(
            "import_job_id", "operation_key", name="uq_imported_operation_job_operation"
        ),
    )
    op.create_index(
        "ix_imported_operation_tenant_review",
        "imported_operation",
        ["tenant_id", "review_status"],
        unique=False,
    )
    op.create_table(
        "tool_binding",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("tool_version_id", sa.Uuid(), nullable=False),
        sa.Column("upstream_service_id", sa.Uuid(), nullable=False),
        sa.Column("imported_operation_id", sa.Uuid(), nullable=True),
        sa.Column("binding_type", sa.String(length=32), nullable=False),
        sa.Column("binding_config_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("binding_digest", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="draft", nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
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
            "binding_type IN ('http', 'remote_mcp')", name=op.f("ck_tool_binding_binding_type")
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'published', 'disabled')", name=op.f("ck_tool_binding_status")
        ),
        sa.ForeignKeyConstraint(
            ["imported_operation_id"],
            ["imported_operation.id"],
            name=op.f("fk_tool_binding_imported_operation_id_imported_operation"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f("fk_tool_binding_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tool_version_id"],
            ["tool_version.id"],
            name=op.f("fk_tool_binding_tool_version_id_tool_version"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["upstream_service_id"],
            ["upstream_service.id"],
            name=op.f("fk_tool_binding_upstream_service_id_upstream_service"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tool_binding")),
        sa.UniqueConstraint("tool_version_id", name="uq_tool_binding_tool_version"),
    )
    op.create_index(
        "ix_tool_binding_tenant_status", "tool_binding", ["tenant_id", "status"], unique=False
    )
    # 延后创建循环引用的一侧，确保两张表都已经存在。
    op.create_foreign_key(
        "fk_imported_operation_draft_tool_binding_id_tool_binding",
        "imported_operation",
        "tool_binding",
        ["draft_tool_binding_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    """回滚初始 Schema。"""
    op.drop_constraint(
        "fk_imported_operation_draft_tool_binding_id_tool_binding",
        "imported_operation",
        type_="foreignkey",
    )
    op.drop_index("ix_tool_binding_tenant_status", table_name="tool_binding")
    op.drop_table("tool_binding")
    op.drop_index("ix_imported_operation_tenant_review", table_name="imported_operation")
    op.drop_table("imported_operation")
    op.drop_index(
        "uq_tool_version_one_published",
        table_name="tool_version",
        postgresql_where=sa.text("status = 'published'"),
    )
    op.drop_index("ix_tool_version_tenant_status", table_name="tool_version")
    op.drop_index("ix_tool_version_schema_digest", table_name="tool_version")
    op.drop_table("tool_version")
    op.drop_index("ix_openapi_import_job_upstream_status", table_name="openapi_import_job")
    op.drop_index("ix_openapi_import_job_tenant_digest_created", table_name="openapi_import_job")
    op.drop_table("openapi_import_job")
    op.drop_index("ix_upstream_service_tenant_status", table_name="upstream_service")
    op.drop_table("upstream_service")
    op.drop_index("ix_tool_tenant_namespace", table_name="tool")
    op.drop_table("tool")
    op.drop_table("tenant")
