"""Persistence Integration Test 共用的 Migration 与隔离 Session Fixture。"""

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from alembic import command
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from nexusmcp.infrastructure.persistence.engine import create_engine, create_session_factory
from tests.integration.persistence.database import alembic_config, require_test_database_url

BUSINESS_TABLES = """
    tool_search_reindex_job,
    tool_search_embedding,
    audit_event,
    execution_attempt,
    tool_execution,
    approval_request,
    tool_binding,
    imported_operation,
    openapi_import_job,
    tool_version,
    tool,
    upstream_service,
    tenant
"""


@pytest.fixture
def migrated_database_url() -> str:
    database_url = require_test_database_url()
    command.upgrade(alembic_config(database_url), "head")
    return database_url


@pytest_asyncio.fixture
async def pg_session_factory(
    migrated_database_url: str,
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_engine(migrated_database_url)
    try:
        async with engine.begin() as connection:
            # 安全校验已限定到名称包含 test 的数据库；每个测试从空业务状态开始。
            await connection.execute(text(f"TRUNCATE TABLE {BUSINESS_TABLES} CASCADE"))
        yield create_session_factory(engine)
    finally:
        await engine.dispose()
