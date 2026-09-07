"""共享 Session Manager 的 Root/Scoped Streamable HTTP 路由。"""

from dataclasses import dataclass
from typing import Any

from mcp.server.lowlevel import Server
from mcp.server.streamable_http_manager import (
    DEFAULT_MAX_REQUEST_BODY_SIZE,
    StreamableHTTPASGIApp,
    StreamableHTTPSessionManager,
)
from mcp.server.transport_security import TransportSecuritySettings
from mcp.shared.inbound import MCP_PROTOCOL_VERSION_HEADER
from mcp_types import UNSUPPORTED_PROTOCOL_VERSION
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.types import ASGIApp, Receive, Scope, Send

from nexusmcp.interfaces.mcp.context import MODERN_PROTOCOL_VERSION


@dataclass(frozen=True, slots=True)
class McpHttpTransport:
    app: Starlette
    session_manager: StreamableHTTPSessionManager


def create_mcp_http_transport(
    server: Server[Any],
    *,
    transport_security: TransportSecuritySettings,
) -> McpHttpTransport:
    """让 Root 与动态 Toolset Path 共享协议 Session，但每个请求保留真实 Path Scope。"""

    manager = StreamableHTTPSessionManager(
        app=server,
        json_response=False,
        stateless=False,
        security_settings=transport_security,
        max_request_body_size=DEFAULT_MAX_REQUEST_BODY_SIZE,
    )
    handler = StreamableHTTPASGIApp(manager)
    app = Starlette(
        routes=[
            Route("/mcp", endpoint=handler),
            Route(
                "/mcp/toolsets/{toolset_slug}",
                endpoint=ModernToolsetEndpoint(handler),
            ),
        ]
    )
    return McpHttpTransport(app=app, session_manager=manager)


class ModernToolsetEndpoint:
    """在 SDK Session Manager 前拒绝 Legacy Scoped 请求。"""

    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            headers = {
                key.decode("latin-1").lower(): value.decode("latin-1")
                for key, value in scope.get("headers", ())
            }
            requested_version = headers.get(MCP_PROTOCOL_VERSION_HEADER)
            if requested_version != MODERN_PROTOCOL_VERSION:
                response = JSONResponse(
                    {
                        "jsonrpc": "2.0",
                        "id": None,
                        "error": {
                            "code": UNSUPPORTED_PROTOCOL_VERSION,
                            "message": (
                                f"Scoped Toolset endpoints require MCP {MODERN_PROTOCOL_VERSION}."
                            ),
                            "data": {
                                "errorCode": "unsupported_protocol",
                                "requested": requested_version,
                            },
                        },
                    },
                    status_code=400,
                )
                await response(scope, receive, send)
                return
        await self._app(scope, receive, send)
