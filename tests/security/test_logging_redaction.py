"""Secret 与任意 Payload 不进入结构化日志的安全回归测试。"""

import io
import logging

from nexusmcp.infrastructure.observability.logging import JsonLogFormatter


def test_sensitive_extra_fields_and_values_are_not_logged() -> None:
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonLogFormatter(service="nexusmcp", environment="test"))
    logger = logging.getLogger("nexusmcp.security.secret_logging")
    logger.handlers.clear()
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    logger.info(
        "secret_logging_probe",
        extra={
            "event": "secret_logging_probe",
            "authorization": "Bearer authorization-secret",
            "cookie": "session=cookie-secret",
            "api_key": "api-key-secret",
            "tool_arguments": {"employee_ssn": "argument-secret"},
        },
    )

    output = stream.getvalue()
    assert "authorization-secret" not in output
    assert "cookie-secret" not in output
    assert "api-key-secret" not in output
    assert "argument-secret" not in output
    assert "authorization" not in output
    assert "tool_arguments" not in output
