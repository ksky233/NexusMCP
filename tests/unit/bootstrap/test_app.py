"""Application Factory 冒烟测试。"""

import httpx
import pytest

from nexusmcp.bootstrap.app import create_app
from nexusmcp.bootstrap.config import Settings
from nexusmcp.shared.errors import NexusMcpError


@pytest.mark.asyncio
async def test_health_routes_are_registered_before_mcp_mount() -> None:
    app = create_app(Settings(environment="test"))
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_host_app_does_not_translate_mcp_errors_as_admin_http_json() -> None:
    app = create_app(Settings(environment="test"))

    # Admin Handler 要注册到未来独立 HTTP 边界，不能覆盖宿主中的 MCP Mount。
    assert NexusMcpError not in app.exception_handlers
