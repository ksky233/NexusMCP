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


class UpstreamNotFoundError(NexusMcpError):
    code = "upstream_not_found"
    safe_message = "The requested upstream service was not found."


class UpstreamConflictError(NexusMcpError):
    code = "upstream_conflict"
    safe_message = "The upstream service conflicts with an existing registration."


class SchemaDigestMismatchError(NexusMcpError):
    code = "schema_digest_mismatch"
    safe_message = "The tool schema no longer matches the reviewed version."


class BindingDigestMismatchError(NexusMcpError):
    code = "binding_digest_mismatch"
    safe_message = "The tool binding no longer matches the reviewed version."


class OpenApiSourceNotFoundError(NexusMcpError):
    code = "openapi_source_not_found"
    safe_message = "The OpenAPI source was not found."


class OpenApiImportJobNotFoundError(NexusMcpError):
    code = "openapi_import_job_not_found"
    safe_message = "The OpenAPI import job was not found."


class OpenApiDocumentInvalidError(NexusMcpError):
    code = "openapi_document_invalid"
    safe_message = "The OpenAPI document is invalid."


class OpenApiFeatureUnsupportedError(NexusMcpError):
    code = "openapi_feature_unsupported"
    safe_message = "The OpenAPI document uses an unsupported feature."


class ImportedOperationNotFoundError(NexusMcpError):
    code = "imported_operation_not_found"
    safe_message = "The imported operation was not found."


class InvalidReviewStateError(NexusMcpError):
    code = "invalid_review_state"
    safe_message = "The imported operation cannot be reviewed from its current state."


class InvalidArgumentsError(NexusMcpError):
    code = "invalid_arguments"
    safe_message = "The request arguments are invalid."


class AuthorizationError(NexusMcpError):
    code = "authorization_denied"
    safe_message = "The principal is not allowed to call this tool."


class AuthenticationError(NexusMcpError):
    code = "authentication_failed"
    safe_message = "The request could not be authenticated."


class ApprovalRequiredError(NexusMcpError):
    code = "approval_required"
    safe_message = "This tool call requires approval."


class CredentialBindingNotFoundError(NexusMcpError):
    code = "credential_binding_not_found"
    safe_message = "No credential binding is available for this tool call."


class CredentialBindingConflictError(NexusMcpError):
    code = "credential_binding_conflict"
    safe_message = "Multiple credential bindings match this tool call."


class CredentialResolutionError(NexusMcpError):
    code = "credential_resolution_failed"
    safe_message = "The upstream credential could not be resolved."


class UpstreamTimeoutError(NexusMcpError):
    code = "upstream_timeout"
    safe_message = "The upstream service did not respond before the timeout."


class UpstreamUnavailableError(NexusMcpError):
    code = "upstream_unavailable"
    safe_message = "The upstream service is unavailable."


class UpstreamResponseError(NexusMcpError):
    code = "upstream_response_error"
    safe_message = "The upstream service returned an invalid response."


class UnknownExecutionOutcomeError(NexusMcpError):
    code = "unknown_execution_outcome"
    safe_message = "The upstream execution outcome could not be determined."
