"""add tool catalog fts

Revision ID: 9a41d8e62f7b
Revises: 65b188208572
Create Date: 2026-08-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "9a41d8e62f7b"
down_revision: str | Sequence[str] | None = "65b188208572"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SEARCH_VECTOR_EXPRESSION = (
    "setweight(to_tsvector('simple'::regconfig, COALESCE(search_name, '')), 'A') || "
    "setweight(to_tsvector('simple'::regconfig, COALESCE(search_tags, '')), 'B') || "
    "setweight(to_tsvector('simple'::regconfig, COALESCE(search_description, '')), 'C')"
)


def upgrade() -> None:
    op.add_column(
        "tool_version",
        sa.Column("search_name", sa.Text(), nullable=False, server_default=""),
    )
    op.add_column(
        "tool_version",
        sa.Column("search_tags", sa.Text(), nullable=False, server_default=""),
    )
    op.add_column(
        "tool_version",
        sa.Column("search_description", sa.Text(), nullable=False, server_default=""),
    )
    op.execute(
        """
        UPDATE tool_version AS version
        SET search_name = concat_ws(' ', tool.namespace, tool.canonical_name, version.display_name),
            search_tags = COALESCE(
                (SELECT string_agg(value, ' ')
                 FROM jsonb_array_elements_text(version.tags_json) AS tags(value)),
                ''
            ),
            search_description = version.description
        FROM tool
        WHERE tool.id = version.tool_id
        """
    )
    op.add_column(
        "tool_version",
        sa.Column(
            "search_vector",
            postgresql.TSVECTOR(),
            sa.Computed(SEARCH_VECTOR_EXPRESSION, persisted=True),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_tool_version_search_vector_gin",
        "tool_version",
        ["search_vector"],
        unique=False,
        postgresql_using="gin",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_tool_version_search_vector_gin",
        table_name="tool_version",
        postgresql_using="gin",
    )
    op.drop_column("tool_version", "search_vector")
    op.drop_column("tool_version", "search_description")
    op.drop_column("tool_version", "search_tags")
    op.drop_column("tool_version", "search_name")
