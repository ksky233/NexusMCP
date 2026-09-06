"""I03-0 Modern Dynamic Toolset Path 与 Legacy 拒绝实验。"""

import importlib
import sys
from pathlib import Path
from typing import cast

import httpx2
import pytest
from fastapi import FastAPI
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from mcp.types import TextContent

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))
experiment = importlib.import_module("examples.mcp_compatibility.toolset_scoped")
MODERN_VERSION = cast(str, experiment.MODERN_VERSION)
app = cast(FastAPI, experiment.app)


async def list_and_call(slug: str, tool_name: str) -> tuple[str, tuple[str, ...], str]:
    asgi_transport = httpx2.ASGITransport(app=app)
    async with httpx2.AsyncClient(
        transport=asgi_transport,
        base_url="http://testserver",
    ) as http_client:
        transport = streamable_http_client(
            f"http://testserver/mcp/toolsets/{slug}",
            http_client=http_client,
        )
        async with Client(transport) as client:
            listed = await client.list_tools(cache_mode="refresh")
            called = await client.call_tool(tool_name, {})
            texts = [block.text for block in called.content if isinstance(block, TextContent)]
            return (
                client.protocol_version,
                tuple(tool.name for tool in listed.tools),
                texts[0],
            )


@pytest.mark.asyncio
async def test_modern_dynamic_path_scopes_list_and_call_by_toolset_slug() -> None:
    async with app.router.lifespan_context(app):
        operations = await list_and_call("operations", "operations.get_incident")
        risk_operations = await list_and_call("risk-operations", "risk.get_score")
        transport = httpx2.ASGITransport(app=app)
        async with httpx2.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            legacy_response = await client.post(
                "/mcp/toolsets/operations",
                headers={
                    "accept": "application/json, text/event-stream",
                    "content-type": "application/json",
                    "mcp-protocol-version": "2025-11-25",
                },
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2025-11-25",
                        "capabilities": {},
                        "clientInfo": {"name": "legacy-probe", "version": "0.1.0"},
                    },
                },
            )

    assert operations == (
        MODERN_VERSION,
        ("operations.get_incident",),
        "operations:operations.get_incident",
    )
    assert risk_operations == (
        MODERN_VERSION,
        ("operations.get_incident", "risk.get_score"),
        "risk-operations:risk.get_score",
    )
    assert legacy_response.status_code == 400
    assert legacy_response.json()["error"]["data"] == {
        "errorCode": "unsupported_protocol",
        "requested": "2025-11-25",
    }
