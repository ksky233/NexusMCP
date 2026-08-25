"""Database Runtime 未启动边界与 Reader 防误用测试。"""

import pytest

from nexusmcp.infrastructure.persistence.runtime import DatabaseRuntime
from nexusmcp.modules.catalog.adapters.sqlalchemy_reader import SqlAlchemyPublishedToolReader

DATABASE_URL = "postgresql+asyncpg://nexusmcp:test@127.0.0.1:55432/nexusmcp_test"


@pytest.mark.asyncio
async def test_runtime_is_not_ready_before_start_and_stop_is_idempotent() -> None:
    runtime = DatabaseRuntime(DATABASE_URL)

    assert runtime.is_started is False
    assert await runtime.is_ready() is False
    await runtime.stop()
    assert runtime.is_started is False


@pytest.mark.asyncio
async def test_reader_rejects_query_before_database_lifespan_starts() -> None:
    runtime = DatabaseRuntime(DATABASE_URL)
    reader = SqlAlchemyPublishedToolReader(runtime)

    with pytest.raises(RuntimeError, match="not started"):
        await reader.list_published_by_tenant("tenant-a")


def test_runtime_requires_positive_readiness_timeout() -> None:
    with pytest.raises(ValueError, match="must be positive"):
        DatabaseRuntime(DATABASE_URL, readiness_timeout_seconds=0)
