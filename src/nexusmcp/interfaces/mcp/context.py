"""将 SDK 请求上下文转换成协议无关的 RequestContext。"""

import re
import uuid
from collections.abc import Mapping
from typing import Any, cast

from mcp.server.context import ServerRequestContext

from nexusmcp.modules.identity.domain import InternalPrincipal, PrincipalType
from nexusmcp.modules.toolsets.runtime import McpEndpointScope
from nexusmcp.shared.request_context import (
    ANONYMOUS_PRINCIPAL_ID,
    ProtocolEra,
    RequestContext,
)

MODERN_PROTOCOL_VERSION = "2026-07-28"
_TRACEPARENT_PATTERN = re.compile(r"^[\da-fA-F]{2}-([\da-fA-F]{32})-[\da-fA-F]{16}-[\da-fA-F]{2}$")


def request_headers(ctx: ServerRequestContext[Any, Any]) -> Mapping[str, str]:
    request = ctx.request
    headers = getattr(request, "headers", None)
    if not isinstance(headers, Mapping):
        return {}
    return {str(key).lower(): str(value) for key, value in cast(Mapping[Any, Any], headers).items()}


def resolve_endpoint_scope(ctx: ServerRequestContext[Any, Any]) -> McpEndpointScope:
    """只信任 Starlette Router 解析出的 Path Param，不接受 Agent 自报 Toolset。"""

    request = ctx.request
    path_params = getattr(request, "path_params", None)
    if not isinstance(path_params, Mapping):
        return McpEndpointScope.root()
    slug = path_params.get("toolset_slug")
    if slug is None:
        return McpEndpointScope.root()
    if not isinstance(slug, str) or not slug:
        raise ValueError("toolset endpoint path contained an invalid slug")
    return McpEndpointScope.toolset(slug)


def _trace_id(headers: Mapping[str, str]) -> str:
    traceparent = headers.get("traceparent", "")
    match = _TRACEPARENT_PATTERN.fullmatch(traceparent)
    return match.group(1).lower() if match else uuid.uuid4().hex


def resolve_request_context(
    ctx: ServerRequestContext[Any, Any],
    *,
    tenant_id: str,
    principal: InternalPrincipal | None = None,
) -> RequestContext:
    """在可信 Authenticator 引入前构造匿名 RequestContext。"""

    headers = request_headers(ctx)
    resolved_principal = principal or InternalPrincipal(
        id=ANONYMOUS_PRINCIPAL_ID,
        tenant_id=tenant_id,
        principal_type=PrincipalType.ANONYMOUS,
        authn_method="anonymous",
    )
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
        principal_id=resolved_principal.id,
        authn_method=resolved_principal.authn_method,
        principal_type=resolved_principal.principal_type.value,
    )
