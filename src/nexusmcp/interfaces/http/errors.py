"""将协议无关应用错误映射为安全 HTTP Response。"""

import logging
from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

from nexusmcp.shared.errors import NexusMcpError
from nexusmcp.shared.log_context import current_log_context

logger = logging.getLogger(__name__)

_HTTP_STATUS_BY_ERROR_CODE = {
    "tool_not_found": HTTPStatus.NOT_FOUND,
    "tool_version_not_found": HTTPStatus.NOT_FOUND,
    "tool_binding_not_found": HTTPStatus.NOT_FOUND,
    "toolset_not_found": HTTPStatus.NOT_FOUND,
    "openapi_source_not_found": HTTPStatus.NOT_FOUND,
    "openapi_import_job_not_found": HTTPStatus.NOT_FOUND,
    "imported_operation_not_found": HTTPStatus.NOT_FOUND,
    "upstream_not_found": HTTPStatus.NOT_FOUND,
    "tool_not_visible": HTTPStatus.FORBIDDEN,
    "tenant_boundary_violation": HTTPStatus.FORBIDDEN,
    "invalid_tool_state": HTTPStatus.CONFLICT,
    "publish_conflict": HTTPStatus.CONFLICT,
    "toolset_conflict": HTTPStatus.CONFLICT,
    "toolset_revision_conflict": HTTPStatus.CONFLICT,
    "toolset_member_unavailable": HTTPStatus.CONFLICT,
    "system_toolset_immutable": HTTPStatus.CONFLICT,
    "invalid_toolset_members": HTTPStatus.UNPROCESSABLE_ENTITY,
    "upstream_not_active": HTTPStatus.CONFLICT,
    "schema_digest_mismatch": HTTPStatus.CONFLICT,
    "binding_digest_mismatch": HTTPStatus.CONFLICT,
    "invalid_review_state": HTTPStatus.CONFLICT,
    "openapi_feature_unsupported": HTTPStatus.UNPROCESSABLE_ENTITY,
    "upstream_conflict": HTTPStatus.CONFLICT,
    "feature_not_enabled": HTTPStatus.NOT_IMPLEMENTED,
    "authorization_denied": HTTPStatus.FORBIDDEN,
    "authentication_failed": HTTPStatus.UNAUTHORIZED,
    "approval_required": HTTPStatus.ACCEPTED,
    "approval_not_found": HTTPStatus.NOT_FOUND,
    "approval_pending": HTTPStatus.CONFLICT,
    "approval_rejected": HTTPStatus.CONFLICT,
    "approval_expired": HTTPStatus.CONFLICT,
    "approval_already_consumed": HTTPStatus.CONFLICT,
    "approval_mismatch": HTTPStatus.CONFLICT,
    "approval_invalid_state": HTTPStatus.CONFLICT,
    "credential_binding_not_found": HTTPStatus.NOT_FOUND,
    "credential_binding_conflict": HTTPStatus.CONFLICT,
    "credential_resolution_failed": HTTPStatus.BAD_GATEWAY,
    "upstream_timeout": HTTPStatus.GATEWAY_TIMEOUT,
    "upstream_unavailable": HTTPStatus.BAD_GATEWAY,
    "upstream_response_error": HTTPStatus.BAD_GATEWAY,
    "unknown_execution_outcome": HTTPStatus.BAD_GATEWAY,
    "tool_execution_not_found": HTTPStatus.NOT_FOUND,
    "invalid_execution_state": HTTPStatus.CONFLICT,
    "execution_attempt_not_found": HTTPStatus.NOT_FOUND,
    "idempotency_key_required": HTTPStatus.UNPROCESSABLE_ENTITY,
    "idempotency_conflict": HTTPStatus.CONFLICT,
    "idempotency_in_progress": HTTPStatus.CONFLICT,
    "idempotency_already_completed": HTTPStatus.CONFLICT,
    "idempotency_outcome_unknown": HTTPStatus.CONFLICT,
    "idempotency_previous_failed": HTTPStatus.CONFLICT,
    "tool_search_mode_unavailable": HTTPStatus.SERVICE_UNAVAILABLE,
    "tool_search_reindex_job_not_found": HTTPStatus.NOT_FOUND,
    "tool_search_reindex_job_conflict": HTTPStatus.CONFLICT,
    "embedding_authentication_failed": HTTPStatus.BAD_GATEWAY,
    "embedding_rate_limited": HTTPStatus.TOO_MANY_REQUESTS,
    "embedding_unavailable": HTTPStatus.SERVICE_UNAVAILABLE,
    "embedding_response_invalid": HTTPStatus.BAD_GATEWAY,
    "unsafe_upstream_endpoint": HTTPStatus.FORBIDDEN,
}


class ProblemFieldError(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field: str
    code: str
    detail: str


class ProblemDetails(BaseModel):
    """RFC 9457 核心字段 + NexusMCP 稳定错误扩展。"""

    model_config = ConfigDict(extra="forbid")

    type: str
    title: str
    status: int
    detail: str
    code: str
    request_id: str | None = None
    errors: tuple[ProblemFieldError, ...] | None = None


def http_status_for(error: NexusMcpError) -> HTTPStatus:
    return _HTTP_STATUS_BY_ERROR_CODE.get(error.code, HTTPStatus.BAD_REQUEST)


def http_error_body(error: NexusMcpError) -> dict[str, Any]:
    """只返回稳定 Code 与安全消息；内部 Exception Message 不进入响应。"""

    status = http_status_for(error).value
    return ProblemDetails(
        type=f"urn:nexusmcp:error:{error.code}",
        title="Request rejected",
        status=status,
        detail=error.safe_message,
        code=error.code,
        request_id=current_log_context().request_id,
    ).model_dump(mode="json", exclude_none=True)


async def nexusmcp_error_handler(_request: Request, error: Exception) -> JSONResponse:
    if not isinstance(error, NexusMcpError):
        raise TypeError("nexusmcp error handler received an unsupported exception")
    logger.warning(
        "http_request_rejected",
        extra={
            "event": "http_request_rejected",
            "error_code": error.code,
        },
    )
    return JSONResponse(
        status_code=http_status_for(error).value,
        content=http_error_body(error),
        media_type="application/problem+json",
    )


async def request_validation_error_handler(
    _request: Request,
    error: Exception,
) -> JSONResponse:
    if not isinstance(error, RequestValidationError):
        raise TypeError("validation error handler received an unsupported exception")
    fields = tuple(
        ProblemFieldError(
            field=_field_path(item.get("loc")),
            code=str(item.get("type", "validation_error")),
            detail=str(item.get("msg", "Invalid value")),
        )
        for item in error.errors()
    )
    status = HTTPStatus.UNPROCESSABLE_ENTITY.value
    problem = ProblemDetails(
        type="urn:nexusmcp:error:request_validation_failed",
        title="Request validation failed",
        status=status,
        detail="The request did not match the expected contract.",
        code="request_validation_failed",
        request_id=current_log_context().request_id,
        errors=fields,
    )
    return JSONResponse(
        status_code=status,
        content=problem.model_dump(mode="json", exclude_none=True),
        media_type="application/problem+json",
    )


def problem_responses(*statuses: int) -> dict[int | str, dict[str, Any]]:
    """为 Admin Route 声明统一 Problem Details，422 始终覆盖请求校验失败。"""

    return {
        status: {
            "model": ProblemDetails,
            "description": HTTPStatus(status).phrase,
            "content": {"application/problem+json": {}},
        }
        for status in sorted({HTTPStatus.UNPROCESSABLE_ENTITY.value, *statuses})
    }


def _field_path(location: object) -> str:
    if not isinstance(location, tuple | list):
        return "request"
    parts = [str(item) for item in location if item not in {"body", "query", "path"}]
    return ".".join(parts) or "request"


def register_http_exception_handlers(app: FastAPI) -> None:
    """注册 Expected Error；Unexpected Error 继续交给 ASGI Server 的安全 500 边界。"""

    app.add_exception_handler(NexusMcpError, nexusmcp_error_handler)
    app.add_exception_handler(RequestValidationError, request_validation_error_handler)
