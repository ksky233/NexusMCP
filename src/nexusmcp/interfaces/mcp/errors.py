"""将内部安全错误映射为 MCP Tool Result。"""

from mcp import types

from nexusmcp.shared.errors import NexusMcpError

ERROR_CODE_META_KEY = "com.nexusmcp/errorCode"


def to_call_tool_error(error: NexusMcpError) -> types.CallToolResult:
    """返回模型可见的安全错误，不暴露内部 Traceback。"""

    return types.CallToolResult(
        content=[types.TextContent(text=error.safe_message)],
        is_error=True,
        _meta={ERROR_CODE_META_KEY: error.code},
    )
