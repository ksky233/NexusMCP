"""标准 Logging 的安全结构化 Formatter 与进程级配置。"""

import json
import logging
import re
import sys
import traceback
from datetime import UTC, datetime
from types import TracebackType
from typing import Any, Literal

from nexusmcp.shared.log_context import current_log_context

type LogFormat = Literal["console", "json"]

_EXTRA_FIELDS = (
    "error_code",
    "duration_ms",
    "tool_count",
)
_EVENT_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
_SENSITIVE_ASSIGNMENT_PATTERN = re.compile(
    r"(?i)(authorization|cookie|api[-_]?key|access[-_]?token|refresh[-_]?token|password|secret)"
    r"[\"']?\s*[:=]\s*[\"']?(?:bearer\s+)?[^\s,;\"']+"
)
_URL_CREDENTIAL_PATTERN = re.compile(r"(?i)(://)[^/@\s:]+:[^/@\s]+@")
_MAX_FIELD_LENGTH = 512


class SafeStructuredFormatter(logging.Formatter):
    """共享字段构造逻辑；不序列化任意 LogRecord Extra。"""

    def __init__(self, *, service: str, environment: str) -> None:
        super().__init__()
        self._service = service
        self._environment = environment

    def structured_record(self, record: logging.LogRecord) -> dict[str, Any]:
        event = getattr(record, "event", record.getMessage())
        normalized_event = _normalize_event(event)
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname.lower(),
            "service": self._service,
            "environment": self._environment,
            "logger": record.name,
            "event": normalized_event,
        }
        payload.update(
            {key: _normalize_value(value) for key, value in current_log_context().fields().items()}
        )
        for field_name in _EXTRA_FIELDS:
            value = getattr(record, field_name, None)
            if value is not None:
                payload[field_name] = _normalize_value(value)
        if record.exc_info is not None:
            payload["exception"] = _safe_exception(record.exc_info)
        return payload


class JsonLogFormatter(SafeStructuredFormatter):
    def format(self, record: logging.LogRecord) -> str:
        return json.dumps(
            self.structured_record(record),
            ensure_ascii=False,
            separators=(",", ":"),
        )


class ConsoleLogFormatter(SafeStructuredFormatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = self.structured_record(record)
        leading = " ".join(
            str(payload.pop(key))
            for key in ("timestamp", "level", "service", "environment", "event")
        )
        details = " ".join(
            f"{key}={json.dumps(value, ensure_ascii=False, separators=(',', ':'))}"
            for key, value in payload.items()
        )
        return f"{leading} {details}" if details else leading


def configure_logging(
    *,
    service: str,
    environment: str,
    level: str = "INFO",
    log_format: LogFormat = "console",
) -> None:
    """替换 Root Handler；只应在进程部署入口调用一次。"""

    numeric_level = logging.getLevelNamesMapping().get(level.upper())
    if numeric_level is None:
        raise ValueError("log level must be a valid Python logging level")
    formatter: logging.Formatter
    if log_format == "json":
        formatter = JsonLogFormatter(service=service, environment=environment)
    else:
        formatter = ConsoleLogFormatter(service=service, environment=environment)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(numeric_level)
    logging.captureWarnings(True)


def _normalize_event(value: object) -> str:
    event = _redact_text(str(value)).strip()
    if _EVENT_PATTERN.fullmatch(event):
        return event
    return "unstructured_log_event"


def _normalize_value(value: object) -> str | int | float | bool | None:
    if value is None or isinstance(value, (int, float, bool)):
        return value
    return _redact_text(str(value)).replace("\r", " ").replace("\n", " ")[:_MAX_FIELD_LENGTH]


def _redact_text(value: str) -> str:
    redacted = _SENSITIVE_ASSIGNMENT_PATTERN.sub(
        lambda match: f"{match.group(1)}=[REDACTED]", value
    )
    return _URL_CREDENTIAL_PATTERN.sub(r"\1[REDACTED]@", redacted)


def _safe_exception(
    exc_info: tuple[
        type[BaseException] | None,
        BaseException | None,
        TracebackType | None,
    ],
) -> dict[str, object]:
    exception_type, _exception, traceback_object = exc_info
    frames = traceback.extract_tb(traceback_object) if traceback_object is not None else []
    return {
        "type": exception_type.__name__ if exception_type is not None else "Exception",
        "stack": [
            {
                "file": frame.filename,
                "line": frame.lineno,
                "function": frame.name,
            }
            for frame in frames
        ],
    }
