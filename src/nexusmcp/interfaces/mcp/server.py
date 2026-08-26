"""基于低层 MCP SDK 的动态 Tool 发现 Adapter。"""

import json
import logging
from time import perf_counter
from typing import Any, Protocol

from mcp import types
from mcp.server.context import ServerRequestContext
from mcp.server.lowlevel import Server

from nexusmcp.interfaces.mcp.context import resolve_request_context
from nexusmcp.interfaces.mcp.errors import to_call_tool_error
from nexusmcp.modules.catalog.use_cases import ListVisibleTools, ListVisibleToolsQuery
from nexusmcp.modules.execution.call_tool import CallTool
from nexusmcp.modules.execution.domain import CallToolCommand
from nexusmcp.shared.errors import NexusMcpError
from nexusmcp.shared.log_context import bind_log_context
from nexusmcp.shared.request_context import RequestContext

type RawServerContext = ServerRequestContext[Any, Any]

logger = logging.getLogger(__name__)


class ContextResolver(Protocol):
    """由应用组装注入、支持认证扩展的 Context Resolver。"""

    def __call__(self, ctx: RawServerContext) -> RequestContext: ...


def _anonymous_local_context(ctx: RawServerContext) -> RequestContext:
    return resolve_request_context(ctx, tenant_id="local")


def create_mcp_server(
    list_visible_tools: ListVisibleTools,
    context_resolver: ContextResolver = _anonymous_local_context,
    call_tool: CallTool | None = None,
) -> Server[Any]:
    """创建 SDK Server，并将 tools/list/call 适配到协议无关 Use Case。"""

    async def on_list_tools(
        ctx: RawServerContext,
        _params: types.PaginatedRequestParams | None,
    ) -> types.ListToolsResult:
        request_context = context_resolver(ctx)
        started_at = perf_counter()
        with bind_log_context(
            request_id=request_context.request_id,
            trace_id=request_context.trace_id,
            tenant_id=request_context.tenant_id,
            protocol_era=request_context.protocol_era.value,
        ):
            try:
                tools = await list_visible_tools.execute(ListVisibleToolsQuery(request_context))
                protocol_tools = [
                    types.Tool(
                        name=tool.canonical_name,
                        title=tool.display_name,
                        description=tool.description,
                        input_schema=dict(tool.input_schema),
                        output_schema=dict(tool.output_schema) if tool.output_schema else None,
                        _meta={
                            "com.nexusmcp/toolId": tool.tool_id,
                            "com.nexusmcp/toolVersionId": tool.tool_version_id,
                            "com.nexusmcp/toolVersion": tool.version,
                        },
                    )
                    for tool in tools
                ]
            except NexusMcpError as error:
                logger.warning(
                    "mcp_request_rejected",
                    extra={
                        "event": "mcp_request_rejected",
                        "error_code": error.code,
                        "duration_ms": round((perf_counter() - started_at) * 1000, 3),
                    },
                )
                raise
            except Exception:
                logger.exception(
                    "mcp_request_failed",
                    extra={
                        "event": "mcp_request_failed",
                        "error_code": "unexpected_error",
                        "duration_ms": round((perf_counter() - started_at) * 1000, 3),
                    },
                )
                raise
            logger.info(
                "mcp_tools_list_completed",
                extra={
                    "event": "mcp_tools_list_completed",
                    "tool_count": len(protocol_tools),
                    "duration_ms": round((perf_counter() - started_at) * 1000, 3),
                },
            )
            return types.ListToolsResult(
                tools=protocol_tools,
                cache_scope="private",
                ttl_ms=0,
            )

    async def on_call_tool(
        ctx: RawServerContext,
        params: types.CallToolRequestParams,
    ) -> types.CallToolResult:
        started_at = perf_counter()
        try:
            request_context = context_resolver(ctx)
        except NexusMcpError as error:
            logger.warning(
                "mcp_authentication_rejected",
                extra={
                    "event": "mcp_authentication_rejected",
                    "error_code": error.code,
                    "duration_ms": round((perf_counter() - started_at) * 1000, 3),
                },
            )
            return to_call_tool_error(error)
        with bind_log_context(
            request_id=request_context.request_id,
            trace_id=request_context.trace_id,
            tenant_id=request_context.tenant_id,
            protocol_era=request_context.protocol_era.value,
        ):
            if call_tool is None:
                return to_call_tool_error(NexusMcpError("tools/call is not configured"))
            try:
                result = await call_tool.execute(
                    CallToolCommand(
                        context=request_context,
                        tool_name=params.name,
                        arguments=params.arguments or {},
                    )
                )
            except NexusMcpError as error:
                logger.warning(
                    "mcp_tool_call_rejected",
                    extra={
                        "event": "mcp_tool_call_rejected",
                        "error_code": error.code,
                        "duration_ms": round((perf_counter() - started_at) * 1000, 3),
                    },
                )
                return to_call_tool_error(error)
            except Exception:
                logger.exception(
                    "mcp_tool_call_failed",
                    extra={
                        "event": "mcp_tool_call_failed",
                        "error_code": "unexpected_error",
                        "duration_ms": round((perf_counter() - started_at) * 1000, 3),
                    },
                )
                return to_call_tool_error(NexusMcpError())

            logger.info(
                "mcp_tool_call_completed",
                extra={
                    "event": "mcp_tool_call_completed",
                    "duration_ms": round((perf_counter() - started_at) * 1000, 3),
                },
            )
            text = (
                result.data
                if isinstance(result.data, str)
                else json.dumps(result.data, ensure_ascii=False, separators=(",", ":"))
            )
            return types.CallToolResult(
                content=[types.TextContent(text=text)],
                structured_content=result.data,
                _meta={
                    "com.nexusmcp/executionId": result.execution_id,
                    "com.nexusmcp/upstreamStatus": result.upstream_status,
                },
            )

    return Server(
        name="nexusmcp",
        title="NexusMCP",
        version="0.1.0",
        description="Enterprise MCP Gateway and Registry",
        on_list_tools=on_list_tools,
        on_call_tool=on_call_tool if call_tool is not None else None,
    )
