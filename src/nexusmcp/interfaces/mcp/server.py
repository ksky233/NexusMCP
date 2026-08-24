"""基于低层 MCP SDK 的动态 Tool 发现 Adapter。"""

from typing import Any, Protocol

from mcp import types
from mcp.server.context import ServerRequestContext
from mcp.server.lowlevel import Server

from nexusmcp.interfaces.mcp.context import resolve_request_context
from nexusmcp.modules.catalog.use_cases import ListVisibleTools, ListVisibleToolsQuery
from nexusmcp.shared.request_context import RequestContext

type RawServerContext = ServerRequestContext[Any, Any]


class ContextResolver(Protocol):
    """由应用组装注入、支持认证扩展的 Context Resolver。"""

    def __call__(self, ctx: RawServerContext) -> RequestContext: ...


def _anonymous_local_context(ctx: RawServerContext) -> RequestContext:
    return resolve_request_context(ctx, tenant_id="local")


def create_mcp_server(
    list_visible_tools: ListVisibleTools,
    context_resolver: ContextResolver = _anonymous_local_context,
) -> Server[Any]:
    """创建 SDK Server，并将 tools/list 适配到 Catalog Use Case。"""

    async def on_list_tools(
        ctx: RawServerContext,
        _params: types.PaginatedRequestParams | None,
    ) -> types.ListToolsResult:
        request_context = context_resolver(ctx)
        tools = await list_visible_tools.execute(ListVisibleToolsQuery(request_context))
        protocol_tools = [
            types.Tool(
                name=tool.canonical_name,
                title=tool.display_name,
                description=tool.description,
                input_schema=dict(tool.input_schema),
                output_schema=dict(tool.output_schema) if tool.output_schema else None,
                _meta={
                    "com.nexusmcp/toolId": tool.id,
                    "com.nexusmcp/toolVersion": tool.version,
                },
            )
            for tool in tools
        ]
        return types.ListToolsResult(
            tools=protocol_tools,
            cache_scope="private",
            ttl_ms=0,
        )

    return Server(
        name="nexusmcp",
        title="NexusMCP",
        version="0.1.0",
        description="Enterprise MCP Gateway and Registry",
        on_list_tools=on_list_tools,
    )
