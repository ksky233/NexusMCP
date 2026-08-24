"""正式动态 MCP Interface Adapter 契约测试。"""

import httpx2
import pytest
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

from nexusmcp.bootstrap.app import create_app
from nexusmcp.bootstrap.config import Settings
from nexusmcp.interfaces.mcp.server import create_mcp_server
from nexusmcp.modules.catalog.adapters.in_memory import InMemoryToolRepository
from nexusmcp.modules.catalog.domain import ToolDefinition, ToolStatus, ToolVisibility
from nexusmcp.modules.catalog.use_cases import ListVisibleTools


def _repository() -> InMemoryToolRepository:
    return InMemoryToolRepository(
        [
            ToolDefinition(
                id="directory-get-employee-v1",
                tenant_id="local",
                canonical_name="directory.get_employee",
                display_name="Get employee",
                description="Get one employee by id.",
                input_schema={
                    "type": "object",
                    "properties": {"employee_id": {"type": "string"}},
                    "required": ["employee_id"],
                    "additionalProperties": False,
                },
                status=ToolStatus.PUBLISHED,
                visibility=ToolVisibility.PUBLIC,
            )
        ]
    )


@pytest.mark.asyncio
async def test_formal_adapter_lists_published_catalog_tools() -> None:
    repository = _repository()
    server = create_mcp_server(ListVisibleTools(repository))

    async with Client(server) as client:
        result = await client.list_tools(cache_mode="refresh")
        protocol_version = client.protocol_version

    assert protocol_version == "2026-07-28"
    assert [tool.name for tool in result.tools] == ["directory.get_employee"]
    assert result.tools[0].input_schema["required"] == ["employee_id"]


@pytest.mark.asyncio
async def test_formal_adapter_is_mounted_at_mcp_endpoint() -> None:
    app = create_app(Settings(environment="test"), _repository())

    async with app.router.lifespan_context(app):
        asgi_transport = httpx2.ASGITransport(app=app)
        async with httpx2.AsyncClient(
            transport=asgi_transport,
            base_url="http://testserver",
        ) as http_client:
            mcp_transport = streamable_http_client(
                "http://testserver/mcp",
                http_client=http_client,
            )
            async with Client(mcp_transport) as client:
                result = await client.list_tools(cache_mode="refresh")

    assert [tool.name for tool in result.tools] == ["directory.get_employee"]
