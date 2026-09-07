"""将内部安全错误映射为 MCP Tool Result。"""

from mcp import types
from mcp.shared.exceptions import MCPError
from mcp_types import INVALID_REQUEST

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


def to_mcp_error(error: NexusMcpError) -> MCPError:
    """为非 Tool Result 方法保留稳定 Error Code，同时只暴露安全消息。"""

    return MCPError(
        code=INVALID_REQUEST,
        message=error.safe_message,
        data={"errorCode": error.code},
    )
