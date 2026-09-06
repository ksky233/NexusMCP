"""I03-0：Modern MCP Dynamic Toolset Path 最小实验。"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI
from mcp import types
from mcp.server.context import ServerRequestContext
from mcp.server.lowlevel import Server
from mcp.server.transport_security import TransportSecuritySettings
from mcp_types import UNSUPPORTED_PROTOCOL_VERSION
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

MODERN_VERSION = "2026-07-28"


@dataclass(frozen=True, slots=True)
class ScopedTool:
    name: str
    description: str


TOOLS = {
    "operations": (ScopedTool("operations.get_incident", "Get one incident."),),
    "risk-operations": (
        ScopedTool("operations.get_incident", "Get one incident."),
        ScopedTool("risk.get_score", "Get one transaction risk score."),
    ),
}


def _toolset_slug(ctx: ServerRequestContext[Any, Any]) -> str:
    request = ctx.request
    path_params = getattr(request, "path_params", None)
    if not isinstance(path_params, dict):
        raise RuntimeError("scoped MCP request did not expose Starlette path parameters")
    slug = path_params.get("toolset_slug")
    if not isinstance(slug, str) or not slug:
        raise RuntimeError("scoped MCP request did not contain a toolset slug")
    return slug


async def list_toolset_tools(
    ctx: ServerRequestContext[Any, Any],
    _params: types.PaginatedRequestParams | None,
) -> types.ListToolsResult:
    slug = _toolset_slug(ctx)
    tools = [
        types.Tool(
            name=tool.name,
            description=tool.description,
            input_schema={"type": "object", "properties": {}},
        )
        for tool in TOOLS.get(slug, ())
    ]
    return types.ListToolsResult(tools=tools, cache_scope="private", ttl_ms=0)


async def call_toolset_tool(
    ctx: ServerRequestContext[Any, Any],
    params: types.CallToolRequestParams,
) -> types.CallToolResult:
    slug = _toolset_slug(ctx)
    member_names = {tool.name for tool in TOOLS.get(slug, ())}
    if params.name not in member_names:
        return types.CallToolResult(
            content=[types.TextContent(text="tool is not a member of the requested toolset")],
            is_error=True,
        )
    return types.CallToolResult(
        content=[types.TextContent(text=f"{slug}:{params.name}")],
    )


server = Server(
    name="nexusmcp-i03-toolset-path",
    version="0.1.0",
    description="Modern-only Dynamic Toolset Path experiment.",
    on_list_tools=list_toolset_tools,
    on_call_tool=call_toolset_tool,
)

transport_security = TransportSecuritySettings(
    allowed_hosts=["testserver", "testserver:*"],
    allowed_origins=[],
)

sdk_app = server.streamable_http_app(
    streamable_http_path="/mcp/toolsets/{toolset_slug}",
    transport_security=transport_security,
)


class ModernToolsetOnly:
    """在进入 SDK Session/Handler 前拒绝 Legacy Scoped Endpoint。"""

    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and str(scope.get("path", "")).startswith("/mcp/toolsets/"):
            headers = {
                key.decode("latin-1").lower(): value.decode("latin-1")
                for key, value in scope.get("headers", ())
            }
            requested_version = headers.get("mcp-protocol-version")
            if requested_version != MODERN_VERSION:
                response = JSONResponse(
                    {
                        "jsonrpc": "2.0",
                        "id": None,
                        "error": {
                            "code": UNSUPPORTED_PROTOCOL_VERSION,
                            "message": "Scoped Toolset endpoints require MCP 2026-07-28.",
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


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    async with server.session_manager.run():
        yield


app = FastAPI(title="NexusMCP I03 Toolset Path Experiment", lifespan=lifespan)
app.mount("/", ModernToolsetOnly(sdk_app))
