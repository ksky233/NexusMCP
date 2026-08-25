"""真实 PostgreSQL Database Runtime 的启动、探针和释放测试。"""

import pytest

from nexusmcp.infrastructure.persistence.runtime import DatabaseRuntime

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_database_runtime_starts_probes_and_disposes(
    migrated_database_url: str,
) -> None:
    runtime = DatabaseRuntime(migrated_database_url)

    await runtime.start()
    assert runtime.is_started is True
    assert await runtime.is_ready() is True
    assert runtime.require_session_factory() is not None

    await runtime.stop()
    assert runtime.is_started is False
    assert await runtime.is_ready() is False
    with pytest.raises(RuntimeError, match="not started"):
        runtime.require_session_factory()


@pytest.mark.asyncio
async def test_database_runtime_cleans_up_after_start_failure() -> None:
    runtime = DatabaseRuntime(
        "postgresql+asyncpg://nexusmcp:nexusmcp_dev@127.0.0.1:1/nexusmcp_test",
        readiness_timeout_seconds=0.2,
    )

    with pytest.raises(OSError):
        await runtime.start()

    assert runtime.is_started is False
    assert await runtime.is_ready() is False
