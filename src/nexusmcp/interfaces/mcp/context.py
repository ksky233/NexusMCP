"""将 SDK 请求上下文转换成协议无关的 RequestContext。"""

import re
import uuid
from collections.abc import Mapping
from typing import Any, cast

from mcp.server.context import ServerRequestContext

from nexusmcp.shared.request_context import (
    ANONYMOUS_PRINCIPAL_ID,
    ProtocolEra,
    RequestContext,
)

MODERN_PROTOCOL_VERSION = "2026-07-28"
_TRACEPARENT_PATTERN = re.compile(r"^[\da-fA-F]{2}-([\da-fA-F]{32})-[\da-fA-F]{16}-[\da-fA-F]{2}$")


def _headers(ctx: ServerRequestContext[Any, Any]) -> Mapping[str, str]:
    request = ctx.request
    headers = getattr(request, "headers", None)
    return cast(Mapping[str, str], headers) if isinstance(headers, Mapping) else {}


def _trace_id(headers: Mapping[str, str]) -> str:
    traceparent = headers.get("traceparent", "")
    match = _TRACEPARENT_PATTERN.fullmatch(traceparent)
    return match.group(1).lower() if match else uuid.uuid4().hex


def resolve_request_context(
    ctx: ServerRequestContext[Any, Any],
    *,
    tenant_id: str,
) -> RequestContext:
    """在可信 Authenticator 引入前构造匿名 RequestContext。"""

    headers = _headers(ctx)
    protocol_era = (
        ProtocolEra.MODERN
        if ctx.protocol_version == MODERN_PROTOCOL_VERSION
        else ProtocolEra.LEGACY
    )
    return RequestContext(
        request_id=str(ctx.request_id if ctx.request_id is not None else uuid.uuid4()),
        trace_id=_trace_id(headers),
        protocol_version=ctx.protocol_version,
        protocol_era=protocol_era,
        tenant_id=tenant_id,
        principal_id=ANONYMOUS_PRINCIPAL_ID,
        authn_method="anonymous",
    )
