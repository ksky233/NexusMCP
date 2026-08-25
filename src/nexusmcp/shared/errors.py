"""协议无关、对外消息安全的应用错误契约。"""

from typing import ClassVar


class NexusMcpError(Exception):
    """业务可预期错误；内部诊断消息与客户端安全消息严格分离。"""

    code: ClassVar[str] = "nexusmcp_error"
    safe_message: ClassVar[str] = "The request could not be completed."

    def __init__(self, internal_message: str | None = None) -> None:
        super().__init__(internal_message or self.safe_message)


class ToolNotFoundError(NexusMcpError):
    code = "tool_not_found"
    safe_message = "The requested tool was not found."


class ToolVersionNotFoundError(NexusMcpError):
    code = "tool_version_not_found"
    safe_message = "The requested tool version was not found."


class ToolBindingNotFoundError(NexusMcpError):
    code = "tool_binding_not_found"
    safe_message = "The requested tool binding was not found."


class ToolNotVisibleError(NexusMcpError):
    code = "tool_not_visible"
    safe_message = "The requested tool is not available to this principal."


class InvalidToolStateError(NexusMcpError):
    code = "invalid_tool_state"
    safe_message = "The tool cannot be changed from its current state."


class TenantBoundaryViolationError(NexusMcpError):
    code = "tenant_boundary_violation"
    safe_message = "The requested resource is not available in this tenant."


class PublishConflictError(NexusMcpError):
    code = "publish_conflict"
    safe_message = "The tool could not be published because its state changed."


class UpstreamNotActiveError(NexusMcpError):
    code = "upstream_not_active"
    safe_message = "The tool upstream is not active."


class SchemaDigestMismatchError(NexusMcpError):
    code = "schema_digest_mismatch"
    safe_message = "The tool schema no longer matches the reviewed version."


class BindingDigestMismatchError(NexusMcpError):
    code = "binding_digest_mismatch"
    safe_message = "The tool binding no longer matches the reviewed version."
