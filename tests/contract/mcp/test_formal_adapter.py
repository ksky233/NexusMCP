"""正式动态 MCP Interface Adapter 契约测试。"""

import httpx2
import pytest
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

from nexusmcp.bootstrap.app import create_app
from nexusmcp.bootstrap.config import Settings
from nexusmcp.interfaces.mcp.server import create_mcp_server
from nexusmcp.modules.catalog.adapters.in_memory import InMemoryToolCatalogRepository
from nexusmcp.modules.catalog.domain import PublishedTool, ToolSideEffect, ToolVisibility
from nexusmcp.modules.catalog.use_cases import ListVisibleTools


def _repository() -> InMemoryToolCatalogRepository:
    return InMemoryToolCatalogRepository(
        published_tools=[
            PublishedTool(
                tool_id="directory-get-employee",
                tool_version_id="directory-get-employee-v1",
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
                output_schema=None,
                version=1,
                visibility=ToolVisibility.PUBLIC,
                side_effect=ToolSideEffect.READ_ONLY,
                schema_digest="directory-get-employee-v1",
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
async def test_search_first_lists_only_meta_tool_and_returns_activatable_schema() -> None:
    app = create_app(
        Settings(environment="test", tool_discovery_mode="search_first"),
        _repository(),
    )

    async with app.router.lifespan_context(app):
        transport = httpx2.ASGITransport(app=app)
        async with httpx2.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as http_client:
            mcp_transport = streamable_http_client(
                "http://testserver/mcp",
                http_client=http_client,
            )
            async with Client(mcp_transport) as client:
                listed = await client.list_tools(cache_mode="refresh")
                searched = await client.call_tool(
                    "nexus.search_tools",
                    {
                        "query": "employee",
                        "retrieval_mode": "lexical",
                        "limit": 5,
                    },
                )
                hybrid = await client.call_tool(
                    "nexus.search_tools",
                    {"query": "find a person", "retrieval_mode": "hybrid"},
                )

    assert [tool.name for tool in listed.tools] == ["nexus.search_tools"]
    assert listed.tools[0].input_schema["required"] == ["query", "retrieval_mode"]
    assert listed.tools[0].input_schema["properties"]["retrieval_mode"]["enum"] == [
        "lexical",
        "hybrid",
    ]
    assert searched.is_error is False
    assert searched.structured_content["tools"][0]["name"] == "directory.get_employee"
    assert searched.structured_content["tools"][0]["inputSchema"]["required"] == ["employee_id"]
    assert hybrid.is_error is True
    assert hybrid.meta is not None
    assert hybrid.meta["com.nexusmcp/errorCode"] == "tool_search_mode_unavailable"


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

    assert [tool.name for tool in result.tools] == [
        "nexus.search_tools",
        "directory.get_employee",
    ]


@pytest.mark.asyncio
async def test_formal_legacy_adapter_omits_modern_array_output_schema() -> None:
    repository = InMemoryToolCatalogRepository(
        published_tools=[
            PublishedTool(
                tool_id="directory-list-employees",
                tool_version_id="directory-list-employees-v1",
                tenant_id="local",
                canonical_name="directory.list_employees",
                display_name="List employees",
                description="List employees.",
                input_schema={"type": "object", "properties": {}},
                output_schema={
                    "type": "array",
                    "items": {"type": "object"},
                },
                version=1,
                visibility=ToolVisibility.PUBLIC,
                side_effect=ToolSideEffect.READ_ONLY,
                schema_digest="2" * 64,
            )
        ]
    )
    app = create_app(Settings(environment="test"), repository)

    async with app.router.lifespan_context(app):
        transport = httpx2.ASGITransport(app=app)
        async with httpx2.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as http_client:
            modern_transport = streamable_http_client(
                "http://testserver/mcp",
                http_client=http_client,
            )
            async with Client(modern_transport) as modern_client:
                modern = await modern_client.list_tools(cache_mode="refresh")
            legacy_transport = streamable_http_client(
                "http://testserver/mcp",
                http_client=http_client,
            )
            async with Client(legacy_transport, mode="legacy") as legacy_client:
                legacy = await legacy_client.list_tools(cache_mode="refresh")

    modern_tool = next(tool for tool in modern.tools if tool.name == "directory.list_employees")
    legacy_tool = next(tool for tool in legacy.tools if tool.name == "directory.list_employees")
    assert modern_tool.output_schema == {"type": "array", "items": {"type": "object"}}
    assert legacy_tool.output_schema is None
