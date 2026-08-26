"""将内部安全错误映射为 MCP Tool Result。"""

from mcp import types

from nexusmcp.shared.errors import IdempotencyExecutionError, NexusMcpError

ERROR_CODE_META_KEY = "com.nexusmcp/errorCode"
EXISTING_EXECUTION_ID_META_KEY = "com.nexusmcp/existingExecutionId"


def to_call_tool_error(error: NexusMcpError) -> types.CallToolResult:
    """返回模型可见的安全错误，不暴露内部 Traceback。"""

    metadata: dict[str, object] = {ERROR_CODE_META_KEY: error.code}
    if isinstance(error, IdempotencyExecutionError):
        metadata[EXISTING_EXECUTION_ID_META_KEY] = error.execution_id
    return types.CallToolResult(
        content=[types.TextContent(text=error.safe_message)],
        is_error=True,
        _meta=metadata,
    )
