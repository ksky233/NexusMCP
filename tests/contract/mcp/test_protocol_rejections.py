"""Modern MCP HTTP Boundary 的确定性 JSON-RPC 拒绝契约。"""

from typing import Any

import httpx2
import pytest
from mcp_types import (
    CLIENT_CAPABILITIES_META_KEY,
    HEADER_MISMATCH,
    METHOD_NOT_FOUND,
    PARSE_ERROR,
    PROTOCOL_VERSION_META_KEY,
    UNSUPPORTED_PROTOCOL_VERSION,
)

from nexusmcp.bootstrap.app import create_app
from nexusmcp.bootstrap.config import Settings

MODERN_VERSION = "2026-07-28"


def request_body(
    method: str,
    *,
    request_id: int = 1,
    protocol_version: str = MODERN_VERSION,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": method,
        "params": {
            **(params or {}),
            "_meta": {
                PROTOCOL_VERSION_META_KEY: protocol_version,
                CLIENT_CAPABILITIES_META_KEY: {},
            },
        },
    }


def request_headers(
    method: str,
    *,
    protocol_version: str = MODERN_VERSION,
) -> dict[str, str]:
    return {
        "accept": "application/json, text/event-stream",
        "content-type": "application/json",
        "mcp-protocol-version": protocol_version,
        "mcp-method": method,
    }


@pytest.mark.asyncio
async def test_modern_http_rejects_parse_method_header_and_version_errors() -> None:
    app = create_app(Settings(environment="test"))
    async with app.router.lifespan_context(app):
        transport = httpx2.ASGITransport(app=app)
        async with httpx2.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            parse_error = await client.post(
                "/mcp",
                content=b'{"jsonrpc":"2.0",',
                headers=request_headers("tools/list"),
            )
            unknown_method = await client.post(
                "/mcp",
                json=request_body("nexus/unknown"),
                headers=request_headers("nexus/unknown"),
            )
            header_mismatch = await client.post(
                "/mcp",
                json=request_body("tools/list"),
                headers=request_headers("tools/call"),
            )
            unsupported_version = "2099-01-01"
            unsupported = await client.post(
                "/mcp",
                json=request_body(
                    "tools/list",
                    protocol_version=unsupported_version,
                ),
                headers=request_headers(
                    "tools/list",
                    protocol_version=unsupported_version,
                ),
            )

    assert parse_error.status_code == 400
    assert parse_error.json()["error"]["code"] == PARSE_ERROR
    assert parse_error.json()["id"] is None
    assert unknown_method.status_code == 404
    assert unknown_method.json()["error"]["code"] == METHOD_NOT_FOUND
    assert header_mismatch.status_code == 400
    assert header_mismatch.json()["error"]["code"] == HEADER_MISMATCH
    assert unsupported.status_code == 400
    assert unsupported.json()["error"]["code"] == UNSUPPORTED_PROTOCOL_VERSION
    assert unsupported.json()["error"]["data"]["requested"] == unsupported_version
