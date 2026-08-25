"""Application Factory 冒烟测试。"""

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from nexusmcp.bootstrap.app import create_app
from nexusmcp.bootstrap.config import Settings
from nexusmcp.modules.catalog.adapters.in_memory import InMemoryToolCatalogRepository
from nexusmcp.shared.errors import NexusMcpError


class FakeDatabaseRuntime:
    def __init__(self, *, ready: bool = True, fail_start: bool = False) -> None:
        self.ready = ready
        self.fail_start = fail_start
        self.start_count = 0
        self.stop_count = 0

    async def start(self) -> None:
        self.start_count += 1
        if self.fail_start:
            raise RuntimeError("simulated database startup failure")

    async def stop(self) -> None:
        self.stop_count += 1

    async def is_ready(self) -> bool:
        return self.ready and self.start_count > self.stop_count

    def require_session_factory(self) -> async_sessionmaker[AsyncSession]:
        raise RuntimeError("fake runtime does not provide sessions")


@pytest.mark.asyncio
async def test_health_routes_are_registered_before_mcp_mount() -> None:
    app = create_app(Settings(environment="test", catalog_backend="memory"))
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/health")
        readiness = await client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert readiness.status_code == 200
    assert readiness.json() == {"status": "ok"}


def test_host_app_does_not_translate_mcp_errors_as_admin_http_json() -> None:
    app = create_app(Settings(environment="test", catalog_backend="memory"))

    # Admin Handler 要注册到未来独立 HTTP 边界，不能覆盖宿主中的 MCP Mount。
    assert NexusMcpError not in app.exception_handlers


@pytest.mark.asyncio
async def test_database_runtime_is_owned_by_application_lifespan() -> None:
    runtime = FakeDatabaseRuntime()
    app = create_app(
        Settings(environment="test", catalog_backend="memory"),
        InMemoryToolCatalogRepository(),
        runtime,
    )

    assert runtime.start_count == 0
    async with app.router.lifespan_context(app):
        assert runtime.start_count == 1
        assert runtime.stop_count == 0

    assert runtime.stop_count == 1


@pytest.mark.asyncio
async def test_liveness_stays_up_while_database_readiness_is_down() -> None:
    runtime = FakeDatabaseRuntime(ready=False)
    app = create_app(
        Settings(environment="test", catalog_backend="memory"),
        InMemoryToolCatalogRepository(),
        runtime,
    )

    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            liveness = await client.get("/health/live")
            readiness = await client.get("/health/ready")

    assert liveness.status_code == 200
    assert liveness.json() == {"status": "ok"}
    assert readiness.status_code == 503
    assert readiness.json() == {"status": "not_ready"}


@pytest.mark.asyncio
async def test_database_start_failure_aborts_application_startup() -> None:
    runtime = FakeDatabaseRuntime(fail_start=True)
    app = create_app(
        Settings(environment="test", catalog_backend="memory"),
        InMemoryToolCatalogRepository(),
        runtime,
    )

    with pytest.raises(RuntimeError, match="database startup failure"):
        async with app.router.lifespan_context(app):
            pytest.fail("application must not yield when database startup fails")

    assert runtime.start_count == 1
    assert runtime.stop_count == 0
