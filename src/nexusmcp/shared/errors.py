"""内部安全错误基类。"""


class NexusMcpError(Exception):
    code = "nexusmcp_error"
    safe_message = "The request could not be completed."


class ToolNotFoundError(NexusMcpError):
    code = "tool_not_found"
    safe_message = "The requested tool was not found."


class ToolNotVisibleError(NexusMcpError):
    code = "tool_not_visible"
    safe_message = "The requested tool is not available to this principal."
