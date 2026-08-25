"""将协议无关应用错误映射为安全 HTTP Response。"""

import logging
from http import HTTPStatus

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from nexusmcp.shared.errors import NexusMcpError
from nexusmcp.shared.log_context import current_log_context

logger = logging.getLogger(__name__)

_HTTP_STATUS_BY_ERROR_CODE = {
    "tool_not_found": HTTPStatus.NOT_FOUND,
    "tool_version_not_found": HTTPStatus.NOT_FOUND,
    "tool_binding_not_found": HTTPStatus.NOT_FOUND,
    "openapi_source_not_found": HTTPStatus.NOT_FOUND,
    "imported_operation_not_found": HTTPStatus.NOT_FOUND,
    "tool_not_visible": HTTPStatus.FORBIDDEN,
    "tenant_boundary_violation": HTTPStatus.FORBIDDEN,
    "invalid_tool_state": HTTPStatus.CONFLICT,
    "publish_conflict": HTTPStatus.CONFLICT,
    "upstream_not_active": HTTPStatus.CONFLICT,
    "schema_digest_mismatch": HTTPStatus.CONFLICT,
    "binding_digest_mismatch": HTTPStatus.CONFLICT,
    "invalid_review_state": HTTPStatus.CONFLICT,
    "openapi_feature_unsupported": HTTPStatus.UNPROCESSABLE_ENTITY,
}


def http_status_for(error: NexusMcpError) -> HTTPStatus:
    return _HTTP_STATUS_BY_ERROR_CODE.get(error.code, HTTPStatus.BAD_REQUEST)


def http_error_body(error: NexusMcpError) -> dict[str, str | None]:
    """只返回稳定 Code 与安全消息；内部 Exception Message 不进入响应。"""

    return {
        "code": error.code,
        "message": error.safe_message,
        "request_id": current_log_context().request_id,
    }


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
    )


def register_http_exception_handlers(app: FastAPI) -> None:
    """注册 Expected Error；Unexpected Error 继续交给 ASGI Server 的安全 500 边界。"""

    app.add_exception_handler(NexusMcpError, nexusmcp_error_handler)
