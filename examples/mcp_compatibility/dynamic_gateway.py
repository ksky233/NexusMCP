"""E2: prove that SDK v2 can expose database-shaped tools dynamically."""

from dataclasses import dataclass
from typing import Any

from mcp import types
from mcp.server.context import ServerRequestContext
from mcp.server.lowlevel import Server

# 这两个身份入口只用于 S1 实验：
# - In-Memory Transport 没有 HTTP Request，通过 MCP _meta 模拟身份；
# - Streamable HTTP 通过测试 Header 模拟身份。
# 正式项目必须先验证 Token，再生成可信 Principal，不能直接相信这两个值。
PRINCIPAL_META_KEY = "com.nexusmcp.dev/principal"
PRINCIPAL_HEADER = "x-nexusmcp-s1-principal"


@dataclass(frozen=True)
class ContextObservation:
    """测试探针：记录 SDK 交给低层 Handler 的 Request Context。"""

    protocol_version: str
    method: str
    request_id: str
    principal: str
    has_http_request: bool
    traceparent: str | None
    mcp_session_id: str | None


# 仅用于测试断言，不是正式的 Trace/Audit 存储，也不适用于并发生产请求。
CONTEXT_OBSERVATIONS: list[ContextObservation] = []


@dataclass(frozen=True)
class CatalogTool:
    """内存版 ToolDefinition，模拟未来从 PostgreSQL Catalog 读取的数据。"""

    name: str
    description: str
    input_schema: dict[str, Any]
    visible_to: frozenset[str]


# 这里故意直接保存 JSON Schema，而不是从 Python 函数签名生成。
# 这正是 OpenAPI 导入并发布 Tool 后，NexusMCP 运行时需要处理的数据形态。
TOOLS = (
    CatalogTool(
        name="directory.get_employee",
        description="Get an employee from the in-memory S1 catalog.",
        input_schema={
            "type": "object",
            "properties": {"employee_id": {"type": "string"}},
            "required": ["employee_id"],
            "additionalProperties": False,
        },
        visible_to=frozenset({"viewer", "operator"}),
    ),
    CatalogTool(
        name="ops.get_service_status",
        description="Get a service status from the in-memory S1 catalog.",
        input_schema={
            "type": "object",
            "properties": {"service_id": {"type": "string"}},
            "required": ["service_id"],
            "additionalProperties": False,
        },
        visible_to=frozenset({"operator"}),
    ),
)


def _principal(ctx: ServerRequestContext[Any, Any]) -> str:
    """从不同 Transport 的实验输入中提取模拟 Principal。"""

    request = ctx.request
    headers = getattr(request, "headers", None)
    if headers is not None:
        # E3：HTTP 请求存在时，优先读取测试 Header。
        header_principal = headers.get(PRINCIPAL_HEADER)
        if isinstance(header_principal, str):
            return header_principal

    # E2：内存 Transport 没有 Starlette Request，改从开放的 MCP _meta Map 读取。
    meta = ctx.meta or {}
    principal = meta.get(PRINCIPAL_META_KEY)
    return principal if isinstance(principal, str) else "anonymous"


def _observe_context(ctx: ServerRequestContext[Any, Any]) -> None:
    """捕获协议版本、Method、Request ID 和 HTTP Header，证明 Context 接缝可用。"""

    request = ctx.request
    headers = getattr(request, "headers", None)
    traceparent = headers.get("traceparent") if headers is not None else None
    CONTEXT_OBSERVATIONS.append(
        ContextObservation(
            protocol_version=ctx.protocol_version,
            method=ctx.method,
            request_id=str(ctx.request_id),
            principal=_principal(ctx),
            has_http_request=request is not None,
            traceparent=traceparent,
            mcp_session_id=headers.get("mcp-session-id") if headers is not None else None,
        )
    )


def _visible_tools(principal: str) -> tuple[CatalogTool, ...]:
    """极简可见性过滤；正式实现由 Catalog Query + Policy Evaluator 取代。"""

    return tuple(tool for tool in TOOLS if principal in tool.visible_to)


async def list_visible_tools(
    ctx: ServerRequestContext[Any, Any],
    _params: types.PaginatedRequestParams | None,
) -> types.ListToolsResult:
    """低层 tools/list Handler，是未来 ListVisibleTools Use Case 的协议适配器。"""

    _observe_context(ctx)
    # 将领域侧 CatalogTool 映射成 SDK 协议类型；领域模型不应反向依赖 types.Tool。
    tools = [
        types.Tool(
            name=tool.name,
            description=tool.description,
            inputSchema=tool.input_schema,
        )
        for tool in _visible_tools(_principal(ctx))
    ]
    # 结果随 Principal 变化，所以不能声明为 public cache；ttlMs=0 避免实验被缓存干扰。
    return types.ListToolsResult(tools=tools, cacheScope="private", ttlMs=0)


async def call_tool(
    ctx: ServerRequestContext[Any, Any],
    params: types.CallToolRequestParams,
) -> types.CallToolResult:
    """低层 tools/call Handler，是未来 CallTool Use Case 的协议适配器。"""

    _observe_context(ctx)
    # tools/list 的可见性不能替代 tools/call 鉴权：客户端可以绕过 list 直接猜 Tool Name。
    # 因此调用阶段必须重新解析当前 Principal 能否使用这个 Tool。
    visible_by_name = {tool.name: tool for tool in _visible_tools(_principal(ctx))}
    if params.name not in visible_by_name:
        return types.CallToolResult(
            content=[types.TextContent(text="tool is not visible to this principal")],
            isError=True,
        )

    arguments = params.arguments or {}
    # 这里的分支只是 Fake Executor，用来证明任意 Tool Name 可以动态分发。
    # 正式实现会替换为：Tool Repository → ToolBinding → Executor Registry。
    if params.name == "directory.get_employee":
        result = f"employee:{arguments.get('employee_id')}"
    elif params.name == "ops.get_service_status":
        result = f"service:{arguments.get('service_id')}:healthy"
    else:
        return types.CallToolResult(
            content=[types.TextContent(text="tool binding was not found")],
            isError=True,
        )

    return types.CallToolResult(content=[types.TextContent(text=result)])


# 低层 Server 允许把外部生成的精确 JSON Schema 原样返回，并通过公开 Callback
# 接入动态 Catalog；这比运行时增删 @MCPServer.tool() 更适合 NexusMCP。
server = Server(
    name="nexusmcp-s1-dynamic-gateway",
    version="0.1.0",
    description="Low-level dynamic Tool Gateway experiment for NexusMCP S1.",
    on_list_tools=list_visible_tools,
    on_call_tool=call_tool,
)
