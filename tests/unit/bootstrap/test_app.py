"""Application Factory 冒烟测试。"""

import httpx
import pytest

from nexusmcp.bootstrap.app import create_app
from nexusmcp.bootstrap.config import Settings


@pytest.mark.asyncio
async def test_health_routes_are_registered_before_mcp_mount() -> None:
    app = create_app(Settings(environment="test"))
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
