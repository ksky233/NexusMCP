"""结构化日志字段、格式和安全异常信息测试。"""

import io
import json
import logging

import pytest

from nexusmcp.infrastructure.observability.logging import (
    ConsoleLogFormatter,
    JsonLogFormatter,
    configure_logging,
)
from nexusmcp.shared.log_context import bind_log_context


def _logger_with(formatter: logging.Formatter) -> tuple[logging.Logger, io.StringIO]:
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(formatter)
    logger = logging.getLogger(f"nexusmcp.tests.{id(stream)}")
    logger.handlers.clear()
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    return logger, stream


def test_json_log_contains_base_context_and_allowlisted_extra_fields() -> None:
    formatter = JsonLogFormatter(service="nexusmcp", environment="test")
    logger, stream = _logger_with(formatter)

    with bind_log_context(
        request_id="request-1",
        trace_id="a" * 32,
        tenant_id="tenant-a",
        protocol_era="modern",
    ):
        logger.info(
            "tool_published",
            extra={
                "event": "tool_published",
                "error_code": "none",
                "duration_ms": 12.5,
                "ignored_field": "must-not-appear",
            },
        )

    payload = json.loads(stream.getvalue())
    assert payload["service"] == "nexusmcp"
    assert payload["environment"] == "test"
    assert payload["event"] == "tool_published"
    assert payload["request_id"] == "request-1"
    assert payload["trace_id"] == "a" * 32
    assert payload["tenant_id"] == "tenant-a"
    assert payload["protocol_era"] == "modern"
    assert payload["error_code"] == "none"
    assert payload["duration_ms"] == 12.5
    assert "ignored_field" not in payload


def test_exception_log_omits_exception_message_and_keeps_safe_stack() -> None:
    formatter = JsonLogFormatter(service="nexusmcp", environment="test")
    logger, stream = _logger_with(formatter)

    try:
        raise RuntimeError("password=do-not-log-this")
    except RuntimeError:
        logger.exception(
            "unexpected_failure",
            extra={"event": "unexpected_failure", "error_code": "unexpected_error"},
        )

    output = stream.getvalue()
    payload = json.loads(output)
    assert "do-not-log-this" not in output
    assert payload["exception"]["type"] == "RuntimeError"
    assert payload["exception"]["stack"]


def test_console_formatter_uses_same_structured_field_policy() -> None:
    formatter = ConsoleLogFormatter(service="nexusmcp", environment="development")
    logger, stream = _logger_with(formatter)

    with bind_log_context(request_id="request-console"):
        logger.info("catalog_query_completed", extra={"event": "catalog_query_completed"})

    output = stream.getvalue()
    assert "catalog_query_completed" in output
    assert 'request_id="request-console"' in output


def test_configure_logging_rejects_unknown_level() -> None:
    with pytest.raises(ValueError, match="log level"):
        configure_logging(
            service="nexusmcp",
            environment="test",
            level="VERBOSE",
        )
