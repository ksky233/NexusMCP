"""FTS Migration 对既有 ToolVersion 的 Backfill 与 GIN Index 测试。"""

import asyncio
import uuid

import pytest
from alembic import command
from sqlalchemy import text

from nexusmcp.infrastructure.persistence.engine import create_engine
from tests.integration.persistence.database import alembic_config, require_test_database_url

pytestmark = pytest.mark.integration

PRE_FTS_REVISION = "65b188208572"
TENANT_ID = str(uuid.uuid4())
TOOL_ID = str(uuid.uuid4())
VERSION_ID = str(uuid.uuid4())
DIGEST = "1" * 64


async def insert_pre_fts_version(database_url: str) -> None:
    engine = create_engine(database_url)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    f"""
                    INSERT INTO tenant (id, name, status)
                    VALUES ('{TENANT_ID}'::uuid, 'FTS Migration Tenant', 'active')
                    """
                )
            )
            await connection.execute(
                text(
                    f"""
                    INSERT INTO tool (
                        id, tenant_id, namespace, canonical_name, owner, status
                    ) VALUES (
                        '{TOOL_ID}'::uuid,
                        '{TENANT_ID}'::uuid,
                        'inventory',
                        'inventory.reserve_stock',
                        'migration-test',
                        'active'
                    )
                    """
                )
            )
            await connection.execute(
                text(
                    f"""
                    INSERT INTO tool_version (
                        id, tenant_id, tool_id, version, display_name, description,
                        input_schema_json, output_schema_json, schema_digest, tags_json,
                        side_effect, visibility, status, created_by
                    ) VALUES (
                        '{VERSION_ID}'::uuid,
                        '{TENANT_ID}'::uuid,
                        '{TOOL_ID}'::uuid,
                        1,
                        'Reserve stock',
                        'Create a reservation for warehouse stock.',
                        '{{"type":"object","properties":{{}}}}'::jsonb,
                        NULL,
                        '{DIGEST}',
                        '["inventory","write"]'::jsonb,
                        'non_idempotent_write',
                        'public',
                        'draft',
                        'migration-test'
                    )
                    """
                )
            )
    finally:
        await engine.dispose()


async def read_fts_backfill(database_url: str) -> tuple[str, str, str, str]:
    engine = create_engine(database_url)
    try:
        async with engine.connect() as connection:
            row = (
                await connection.execute(
                    text(
                        """
                        SELECT search_name, search_tags, search_description,
                               search_vector::text AS search_vector_text
                        FROM tool_version
                        WHERE id = :version_id
                        """
                    ),
                    {"version_id": VERSION_ID},
                )
            ).one()
            index_definition = await connection.scalar(
                text(
                    """
                    SELECT indexdef
                    FROM pg_indexes
                    WHERE schemaname = current_schema()
                      AND indexname = 'ix_tool_version_search_vector_gin'
                    """
                )
            )
            assert isinstance(index_definition, str)
            return str(row[0]), str(row[1]), str(row[2]), index_definition + str(row[3])
    finally:
        await engine.dispose()


async def cleanup(database_url: str) -> None:
    engine = create_engine(database_url)
    try:
        async with engine.begin() as connection:
            await connection.execute(text("TRUNCATE TABLE tenant CASCADE"))
    finally:
        await engine.dispose()


def test_fts_migration_backfills_existing_versions_and_creates_gin_index() -> None:
    database_url = require_test_database_url()
    config = alembic_config(database_url)
    command.upgrade(config, "head")
    command.downgrade(config, PRE_FTS_REVISION)
    try:
        asyncio.run(insert_pre_fts_version(database_url))
        command.upgrade(config, "head")
        search_name, search_tags, search_description, index_and_vector = asyncio.run(
            read_fts_backfill(database_url)
        )

        assert search_name == "inventory inventory.reserve_stock Reserve stock"
        assert search_tags == "inventory write"
        assert search_description == "Create a reservation for warehouse stock."
        assert "USING gin" in index_and_vector
        assert "reserve" in index_and_vector
        assert "stock" in index_and_vector
    finally:
        command.upgrade(config, "head")
        asyncio.run(cleanup(database_url))
