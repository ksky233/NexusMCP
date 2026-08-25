"""协议无关、支持 async 隔离的结构化日志上下文。"""

from collections.abc import Generator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import asdict, dataclass, replace


@dataclass(frozen=True, slots=True)
class LogContext:
    request_id: str | None = None
    trace_id: str | None = None
    tenant_id: str | None = None
    protocol_era: str | None = None
    tool_id: str | None = None
    tool_version_id: str | None = None

    def fields(self) -> dict[str, str]:
        """只输出已有的白名单字段，不暴露任意 Context 对象。"""

        return {key: value for key, value in asdict(self).items() if value is not None}


_LOG_CONTEXT: ContextVar[LogContext | None] = ContextVar(
    "nexusmcp_log_context",
    default=None,
)


def current_log_context() -> LogContext:
    return _LOG_CONTEXT.get() or LogContext()


@contextmanager
def bind_log_context(
    *,
    request_id: str | None = None,
    trace_id: str | None = None,
    tenant_id: str | None = None,
    protocol_era: str | None = None,
    tool_id: str | None = None,
    tool_version_id: str | None = None,
) -> Generator[LogContext, None, None]:
    """在当前 async Context 上增量绑定字段，并确保退出时恢复旧值。"""

    current = current_log_context()
    updates = {
        key: value
        for key, value in {
            "request_id": request_id,
            "trace_id": trace_id,
            "tenant_id": tenant_id,
            "protocol_era": protocol_era,
            "tool_id": tool_id,
            "tool_version_id": tool_version_id,
        }.items()
        if value is not None
    }
    context = replace(current, **updates)
    token = _LOG_CONTEXT.set(context)
    try:
        yield context
    finally:
        _LOG_CONTEXT.reset(token)
