"""同一业务错误在 MCP/HTTP 边界的安全映射测试。"""

import json

import pytest
from fastapi import FastAPI, Request
from mcp import types

from nexusmcp.interfaces.http.errors import (
    http_error_body,
    http_status_for,
    nexusmcp_error_handler,
    register_http_exception_handlers,
)
from nexusmcp.interfaces.mcp.errors import to_call_tool_error
from nexusmcp.shared.errors import InvalidToolStateError, NexusMcpError, ToolNotFoundError
from nexusmcp.shared.log_context import bind_log_context

INTERNAL_MESSAGE = "postgresql://admin:super-secret@internal/database"


def test_mcp_error_mapping_does_not_expose_internal_message() -> None:
    error = ToolNotFoundError(INTERNAL_MESSAGE)

    result = to_call_tool_error(error)

    assert result.is_error is True
    assert result.meta == {"com.nexusmcp/errorCode": "tool_not_found"}
    assert isinstance(result.content[0], types.TextContent)
    assert result.content[0].text == error.safe_message
    assert "super-secret" not in str(result)


def test_http_error_mapping_uses_status_safe_message_and_request_id() -> None:
    error = InvalidToolStateError(INTERNAL_MESSAGE)

    with bind_log_context(request_id="request-http"):
        body = http_error_body(error)

    assert http_status_for(error).value == 409
    assert body == {
        "code": "invalid_tool_state",
        "message": error.safe_message,
        "request_id": "request-http",
    }
    assert "super-secret" not in str(body)


@pytest.mark.asyncio
async def test_http_exception_handler_returns_safe_json_response() -> None:
    request = Request({"type": "http", "method": "POST", "path": "/admin/tools"})
    error = InvalidToolStateError(INTERNAL_MESSAGE)

    with bind_log_context(request_id="request-handler"):
        response = await nexusmcp_error_handler(request, error)

    response_body = bytes(response.body)
    assert response.status_code == 409
    assert json.loads(response_body) == {
        "code": "invalid_tool_state",
        "message": error.safe_message,
        "request_id": "request-handler",
    }
    assert b"super-secret" not in response_body


def test_http_handler_can_be_registered_on_future_admin_sub_application() -> None:
    admin_app = FastAPI()

    register_http_exception_handlers(admin_app)

    assert NexusMcpError in admin_app.exception_handlers
