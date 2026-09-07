"""基于低层 MCP SDK 的动态 Tool 发现 Adapter。"""

import json
import logging
from collections.abc import Mapping
from dataclasses import replace
from time import perf_counter
from typing import Any, Protocol

from mcp import types
from mcp.server.context import ServerRequestContext
from mcp.server.lowlevel import Server
from mcp.server.request_state import RequestStateBoundary, RequestStateSecurity

from nexusmcp.infrastructure.observability import NexusTelemetry
from nexusmcp.interfaces.mcp.context import (
    request_headers,
    resolve_endpoint_scope,
    resolve_request_context,
)
from nexusmcp.interfaces.mcp.errors import to_call_tool_error, to_mcp_error
from nexusmcp.interfaces.mcp.meta_tools import (
    NEXUS_SEARCH_TOOLS_NAME,
    parse_search_tools_query,
    search_tools_definition,
    search_tools_result,
)
from nexusmcp.modules.approval.use_cases import DecideApproval, DecideApprovalCommand
from nexusmcp.modules.catalog.use_cases import ListVisibleTools, ListVisibleToolsQuery
from nexusmcp.modules.execution.call_tool import CallTool
from nexusmcp.modules.execution.domain import CallToolCommand, is_valid_idempotency_key
from nexusmcp.modules.tool_search.search_tools import SearchTools, SearchToolsResult
from nexusmcp.modules.toolsets.domain import ToolsetDiscoveryMode
from nexusmcp.modules.toolsets.runtime import (
    McpEndpointScopeType,
    ResolvedToolsetAccess,
    ResolveToolsetAccess,
)
from nexusmcp.shared.errors import (
    ApprovalMismatchError,
    ApprovalRequiredError,
    InvalidArgumentsError,
    NexusMcpError,
    ToolsetAccessDeniedError,
)
from nexusmcp.shared.log_context import bind_log_context
from nexusmcp.shared.request_context import RequestContext

type RawServerContext = ServerRequestContext[Any, Any]

logger = logging.getLogger(__name__)

_APPROVAL_INPUT_KEY = "approval"
_APPROVAL_ID_META_KEY = "com.nexusmcp/approvalId"
_APPROVAL_EXPIRES_AT_META_KEY = "com.nexusmcp/approvalExpiresAt"
_IDEMPOTENCY_KEY_META_KEY = "com.nexusmcp/idempotencyKey"


class ContextResolver(Protocol):
    """由应用组装注入、支持认证扩展的 Context Resolver。"""

    def __call__(self, ctx: RawServerContext) -> RequestContext: ...


def _anonymous_local_context(ctx: RawServerContext) -> RequestContext:
    return resolve_request_context(ctx, tenant_id="local")


def create_mcp_server(
    list_visible_tools: ListVisibleTools,
    context_resolver: ContextResolver = _anonymous_local_context,
    call_tool: CallTool | None = None,
    search_tools: SearchTools | None = None,
    search_first: bool = False,
    decide_approval: DecideApproval | None = None,
    telemetry: NexusTelemetry | None = None,
    request_state_security: RequestStateSecurity | None = None,
    resolve_toolset_access: ResolveToolsetAccess | None = None,
) -> Server[Any]:
    """创建 SDK Server，并将 tools/list/call 适配到协议无关 Use Case。"""

    resolved_telemetry = telemetry or NexusTelemetry.noop()

    async def on_list_tools(
        ctx: RawServerContext,
        _params: types.PaginatedRequestParams | None,
    ) -> types.ListToolsResult:
        request_context = context_resolver(ctx)
        started_at = perf_counter()
        with resolved_telemetry.observe_mcp_request(
            operation="tools.list",
            protocol_era=request_context.protocol_era.value,
            tenant_id=request_context.tenant_id,
            principal_type=request_context.principal_type,
            carrier=request_headers(ctx),
        ) as observation:
            request_context = replace(
                request_context,
                trace_id=observation.trace_id or request_context.trace_id,
            )
            with bind_log_context(
                request_id=request_context.request_id,
                trace_id=request_context.trace_id,
                tenant_id=request_context.tenant_id,
                protocol_era=request_context.protocol_era.value,
            ):
                try:
                    access = await _resolve_toolset_access(
                        ctx,
                        request_context,
                        resolve_toolset_access,
                    )
                    effective_search_first = _search_first(access, search_first)
                    tools = (
                        ()
                        if effective_search_first
                        else (
                            access.tools
                            if access is not None
                            else await list_visible_tools.execute(
                                ListVisibleToolsQuery(request_context)
                            )
                        )
                    )
                    protocol_tools = [
                        types.Tool(
                            name=tool.canonical_name,
                            title=tool.display_name,
                            description=tool.description,
                            input_schema=dict(tool.input_schema),
                            output_schema=_protocol_output_schema(
                                tool.output_schema,
                                request_context,
                            ),
                            _meta={
                                "com.nexusmcp/toolId": tool.tool_id,
                                "com.nexusmcp/toolVersionId": tool.tool_version_id,
                                "com.nexusmcp/toolVersion": tool.version,
                            },
                        )
                        for tool in tools
                    ]
                    if search_tools is not None and _meta_search_visible(access, search_first):
                        protocol_tools.insert(0, search_tools_definition())
                except NexusMcpError as error:
                    observation.finish(outcome="rejected", error_code=error.code)
                    logger.warning(
                        "mcp_request_rejected",
                        extra={
                            "event": "mcp_request_rejected",
                            "error_code": error.code,
                            "duration_ms": round((perf_counter() - started_at) * 1000, 3),
                        },
                    )
                    raise to_mcp_error(error) from error
                except Exception:
                    observation.finish(outcome="error", error_code="unexpected_error")
                    logger.exception(
                        "mcp_request_failed",
                        extra={
                            "event": "mcp_request_failed",
                            "error_code": "unexpected_error",
                            "duration_ms": round((perf_counter() - started_at) * 1000, 3),
                        },
                    )
                    raise
                observation.finish(outcome="success")
                logger.info(
                    "mcp_tools_list_completed",
                    extra={
                        "event": "mcp_tools_list_completed",
                        "tool_count": len(protocol_tools),
                        "duration_ms": round((perf_counter() - started_at) * 1000, 3),
                    },
                )
                return types.ListToolsResult(
                    tools=protocol_tools,
                    cache_scope="private",
                    ttl_ms=0,
                )

    async def on_call_tool(
        ctx: RawServerContext,
        params: types.CallToolRequestParams,
    ) -> types.CallToolResult | types.InputRequiredResult:
        started_at = perf_counter()
        try:
            request_context = context_resolver(ctx)
        except NexusMcpError as error:
            logger.warning(
                "mcp_authentication_rejected",
                extra={
                    "event": "mcp_authentication_rejected",
                    "error_code": error.code,
                    "duration_ms": round((perf_counter() - started_at) * 1000, 3),
                },
            )
            return to_call_tool_error(error)
        with resolved_telemetry.observe_mcp_request(
            operation="tools.call",
            protocol_era=request_context.protocol_era.value,
            tenant_id=request_context.tenant_id,
            principal_type=request_context.principal_type,
            carrier=request_headers(ctx),
        ) as observation:
            request_context = replace(
                request_context,
                trace_id=observation.trace_id or request_context.trace_id,
            )
            with bind_log_context(
                request_id=request_context.request_id,
                trace_id=request_context.trace_id,
                tenant_id=request_context.tenant_id,
                protocol_era=request_context.protocol_era.value,
            ):
                try:
                    access = await _resolve_toolset_access(
                        ctx,
                        request_context,
                        resolve_toolset_access,
                    )
                except NexusMcpError as error:
                    observation.finish(outcome="rejected", error_code=error.code)
                    return to_call_tool_error(error)
                if params.name == NEXUS_SEARCH_TOOLS_NAME:
                    if search_tools is None:
                        error = NexusMcpError("Tool search is not configured")
                        observation.finish(outcome="rejected", error_code=error.code)
                        return to_call_tool_error(error)
                    try:
                        if not _meta_search_visible(access, search_first):
                            raise ToolsetAccessDeniedError(
                                "Meta Tool was outside the requested endpoint discovery mode"
                            )
                        query = parse_search_tools_query(
                            request_context,
                            params.arguments or {},
                        )
                        observation.set_search_mode(query.retrieval_mode.value)
                        result = await search_tools.execute(query)
                        if access is not None:
                            result = _filter_search_result(result, access)
                    except NexusMcpError as error:
                        observation.finish(outcome="rejected", error_code=error.code)
                        logger.warning(
                            "mcp_meta_tool_call_rejected",
                            extra={
                                "event": "mcp_meta_tool_call_rejected",
                                "error_code": error.code,
                                "duration_ms": round(
                                    (perf_counter() - started_at) * 1000,
                                    3,
                                ),
                            },
                        )
                        return to_call_tool_error(error)
                    except Exception:
                        observation.finish(outcome="error", error_code="unexpected_error")
                        logger.exception(
                            "mcp_meta_tool_call_failed",
                            extra={
                                "event": "mcp_meta_tool_call_failed",
                                "error_code": "unexpected_error",
                                "duration_ms": round(
                                    (perf_counter() - started_at) * 1000,
                                    3,
                                ),
                            },
                        )
                        return to_call_tool_error(NexusMcpError())
                    observation.finish(outcome="success")
                    logger.info(
                        "mcp_tool_search_completed",
                        extra={
                            "event": "mcp_tool_search_completed",
                            "retrieval_mode": query.retrieval_mode.value,
                            "candidate_count": len(result.hits),
                            "duration_ms": round((perf_counter() - started_at) * 1000, 3),
                        },
                    )
                    return search_tools_result(result)
                if call_tool is None:
                    error = NexusMcpError("tools/call is not configured")
                    observation.finish(outcome="rejected", error_code=error.code)
                    return to_call_tool_error(error)
                try:
                    if access is not None:
                        access.require_business_tool(params.name)
                    await _resolve_interactive_approval(
                        params=params,
                        context=request_context,
                        decide_approval=decide_approval,
                    )
                    result = await call_tool.execute(
                        CallToolCommand(
                            context=request_context,
                            tool_name=params.name,
                            arguments=params.arguments or {},
                            idempotency_key=_idempotency_key(params),
                            approval_id=params.request_state,
                        )
                    )
                except ApprovalRequiredError as error:
                    if error.approval_id is None or request_context.protocol_era.value != "modern":
                        observation.finish(outcome="rejected", error_code=error.code)
                        return to_call_tool_error(error)
                    observation.finish(outcome="input_required")
                    logger.info(
                        "mcp_tool_call_input_required",
                        extra={
                            "event": "mcp_tool_call_input_required",
                            "duration_ms": round((perf_counter() - started_at) * 1000, 3),
                        },
                    )
                    return _approval_input_required(params.name, error)
                except NexusMcpError as error:
                    observation.finish(outcome="rejected", error_code=error.code)
                    logger.warning(
                        "mcp_tool_call_rejected",
                        extra={
                            "event": "mcp_tool_call_rejected",
                            "error_code": error.code,
                            "duration_ms": round((perf_counter() - started_at) * 1000, 3),
                        },
                    )
                    return to_call_tool_error(error)
                except Exception:
                    observation.finish(outcome="error", error_code="unexpected_error")
                    logger.exception(
                        "mcp_tool_call_failed",
                        extra={
                            "event": "mcp_tool_call_failed",
                            "error_code": "unexpected_error",
                            "duration_ms": round((perf_counter() - started_at) * 1000, 3),
                        },
                    )
                    return to_call_tool_error(NexusMcpError())

                observation.finish(outcome="success")
                logger.info(
                    "mcp_tool_call_completed",
                    extra={
                        "event": "mcp_tool_call_completed",
                        "duration_ms": round((perf_counter() - started_at) * 1000, 3),
                    },
                )
                text = (
                    result.data
                    if isinstance(result.data, str)
                    else json.dumps(result.data, ensure_ascii=False, separators=(",", ":"))
                )
                return types.CallToolResult(
                    content=[types.TextContent(text=text)],
                    structured_content=_protocol_structured_content(
                        result.data,
                        request_context,
                    ),
                    _meta={
                        "com.nexusmcp/executionId": result.execution_id,
                        "com.nexusmcp/upstreamStatus": result.upstream_status,
                        "com.nexusmcp/attemptCount": result.attempt_count,
                    },
                )

    server = Server(
        name="nexusmcp",
        title="NexusMCP",
        version="0.1.0",
        description="Enterprise MCP Gateway and Registry",
        on_list_tools=on_list_tools,
        on_call_tool=on_call_tool if call_tool is not None or search_tools is not None else None,
    )
    security = request_state_security or RequestStateSecurity.ephemeral(
        ttl=600,
        audience="nexusmcp",
    )
    # Low-Level Server 不会自动安装 requestState 防篡改边界，必须显式注册。
    server.middleware.append(RequestStateBoundary(security, default_audience="nexusmcp"))
    return server


async def _resolve_toolset_access(
    ctx: RawServerContext,
    request_context: RequestContext,
    resolver: ResolveToolsetAccess | None,
) -> ResolvedToolsetAccess | None:
    if resolver is None:
        return None
    return await resolver.execute(request_context, resolve_endpoint_scope(ctx))


def _search_first(access: ResolvedToolsetAccess | None, root_search_first: bool) -> bool:
    if access is None or access.endpoint_scope.type is McpEndpointScopeType.ROOT:
        return root_search_first
    return access.discovery_mode is ToolsetDiscoveryMode.SEARCH_FIRST


def _meta_search_visible(
    access: ResolvedToolsetAccess | None,
    root_search_first: bool,
) -> bool:
    if access is None or access.endpoint_scope.type is McpEndpointScopeType.ROOT:
        # Root eager 模式保留现有“Meta Tool + 业务 Tool”兼容行为。
        return True
    return _search_first(access, root_search_first)


def _filter_search_result(
    result: SearchToolsResult,
    access: ResolvedToolsetAccess,
) -> SearchToolsResult:
    allowed_ids = access.available_tool_ids
    hits = tuple(hit for hit in result.hits if hit.tool.tool_id in allowed_ids)
    diagnostics = result.diagnostics
    return SearchToolsResult(
        hits=hits,
        retrieval_mode=result.retrieval_mode,
        index_version=result.index_version,
        diagnostics=(
            {
                hit.tool.tool_version_id: diagnostics[hit.tool.tool_version_id]
                for hit in hits
                if hit.tool.tool_version_id in diagnostics
            }
            if diagnostics is not None
            else None
        ),
    )


def _protocol_output_schema(
    schema: Mapping[str, Any] | None,
    context: RequestContext,
) -> dict[str, Any] | None:
    if schema is None:
        return None
    # Legacy 2025-11-25 只接受 object-root Output Schema；该字段可选，省略比伪造对象契约安全。
    if context.protocol_era.value == "legacy" and schema.get("type") != "object":
        return None
    return dict(schema)


def _protocol_structured_content(
    data: Any,
    context: RequestContext,
) -> Any:
    # Legacy 的 structuredContent 仅兼容 Object；Text Content 仍保留完整序列化业务结果。
    if context.protocol_era.value == "legacy" and not isinstance(data, Mapping):
        return None
    return data


async def _resolve_interactive_approval(
    *,
    params: types.CallToolRequestParams,
    context: RequestContext,
    decide_approval: DecideApproval | None,
) -> None:
    responses = params.input_responses
    if responses is None:
        return
    if params.request_state is None or decide_approval is None:
        raise ApprovalMismatchError("approval input was missing trusted request state")
    if set(responses) != {_APPROVAL_INPUT_KEY}:
        raise ApprovalMismatchError("approval input response keys did not match request")
    response = responses[_APPROVAL_INPUT_KEY]
    if not isinstance(response, types.ElicitResult):
        raise ApprovalMismatchError("approval input response had an invalid type")
    if response.action == "accept":
        if response.content is None or response.content.get("approved") is not True:
            raise ApprovalMismatchError("accepted approval input did not confirm approval")
        approved = True
    else:
        approved = False
    await decide_approval.execute(
        DecideApprovalCommand(
            context=context,
            approval_id=params.request_state,
            approved=approved,
        )
    )


def _approval_input_required(
    tool_name: str,
    error: ApprovalRequiredError,
) -> types.InputRequiredResult:
    assert error.approval_id is not None
    return types.InputRequiredResult(
        input_requests={
            _APPROVAL_INPUT_KEY: types.ElicitRequest(
                params=types.ElicitRequestFormParams(
                    message=f"Approve one call to {tool_name}?",
                    requested_schema={
                        "type": "object",
                        "properties": {
                            "approved": {
                                "type": "boolean",
                                "title": "Approve this tool call",
                            }
                        },
                        "required": ["approved"],
                        "additionalProperties": False,
                    },
                )
            )
        },
        request_state=error.approval_id,
        _meta={
            _APPROVAL_ID_META_KEY: error.approval_id,
            _APPROVAL_EXPIRES_AT_META_KEY: error.expires_at,
        },
    )


def _idempotency_key(params: types.CallToolRequestParams) -> str | None:
    metadata = params.meta or {}
    value = metadata.get(_IDEMPOTENCY_KEY_META_KEY)
    if value is None:
        return None
    if not isinstance(value, str) or not is_valid_idempotency_key(value):
        raise InvalidArgumentsError("idempotency key metadata was invalid")
    return value
