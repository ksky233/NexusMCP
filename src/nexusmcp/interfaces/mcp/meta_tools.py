"""NexusMCP 内建 Meta Tool 的协议 Schema 与结果映射。"""

import json
from collections.abc import Mapping
from typing import Any

from mcp import types

from nexusmcp.modules.catalog.domain import PublishedToolSearchHit, ToolSideEffect
from nexusmcp.modules.tool_search.domain import ToolRetrievalMode
from nexusmcp.modules.tool_search.search_tools import SearchToolsQuery, SearchToolsResult
from nexusmcp.shared.errors import InvalidArgumentsError
from nexusmcp.shared.request_context import RequestContext

NEXUS_SEARCH_TOOLS_NAME = "nexus.search_tools"


def search_tools_definition() -> types.Tool:
    return types.Tool(
        name=NEXUS_SEARCH_TOOLS_NAME,
        title="Search enterprise tools",
        description=(
            "Search the visible enterprise Tool Catalog. Use lexical for explicit names, "
            "namespaces, tags, abbreviations, or domain keywords. Use hybrid for fuzzy, "
            "synonymous, or cross-language intent, and when lexical candidates are insufficient."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "minLength": 1, "maxLength": 200},
                "retrieval_mode": {
                    "type": "string",
                    "enum": ["lexical", "hybrid"],
                },
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 10,
                    "default": 5,
                },
                "namespace": {"type": ["string", "null"]},
                "side_effect": {
                    "type": ["string", "null"],
                    "enum": [
                        "read_only",
                        "idempotent_write",
                        "non_idempotent_write",
                        "unknown",
                        None,
                    ],
                },
            },
            "required": ["query", "retrieval_mode"],
            "additionalProperties": False,
        },
        output_schema={
            "type": "object",
            "properties": {
                "retrievalMode": {"type": "string"},
                "tools": {"type": "array", "items": {"type": "object"}},
            },
            "required": ["retrievalMode", "tools"],
        },
        _meta={"com.nexusmcp/builtIn": True},
    )


def parse_search_tools_query(
    context: RequestContext,
    arguments: Mapping[str, Any],
) -> SearchToolsQuery:
    allowed = {"query", "retrieval_mode", "limit", "namespace", "side_effect"}
    if set(arguments) - allowed:
        raise InvalidArgumentsError("Meta Tool search arguments contained unknown fields")
    text = arguments.get("query")
    mode = arguments.get("retrieval_mode")
    limit = arguments.get("limit", 5)
    namespace = arguments.get("namespace")
    raw_side_effect = arguments.get("side_effect")
    if not isinstance(text, str) or not text.strip():
        raise InvalidArgumentsError("Meta Tool search query must not be blank")
    try:
        retrieval_mode = ToolRetrievalMode(mode)
    except (TypeError, ValueError):
        raise InvalidArgumentsError("Meta Tool retrieval mode was invalid") from None
    if isinstance(limit, bool) or not isinstance(limit, int):
        raise InvalidArgumentsError("Meta Tool search limit must be an integer")
    if namespace is not None and not isinstance(namespace, str):
        raise InvalidArgumentsError("Meta Tool search namespace must be a string")
    try:
        side_effect = ToolSideEffect(raw_side_effect) if raw_side_effect is not None else None
    except (TypeError, ValueError):
        raise InvalidArgumentsError("Meta Tool side effect filter was invalid") from None
    return SearchToolsQuery(
        context=context,
        text=text,
        retrieval_mode=retrieval_mode,
        limit=limit,
        namespace=namespace,
        side_effect=side_effect,
    )


def search_tools_result(
    result: SearchToolsResult,
) -> types.CallToolResult:
    tools = [_candidate(hit) for hit in result.hits]
    data: dict[str, Any] = {
        "retrievalMode": result.retrieval_mode.value,
        "tools": tools,
    }
    metadata: dict[str, Any] = {
        "com.nexusmcp/searchStrategyUsed": result.retrieval_mode.value,
        "com.nexusmcp/candidateCount": len(tools),
    }
    if result.index_version is not None:
        metadata["com.nexusmcp/indexVersion"] = result.index_version
    return types.CallToolResult(
        content=[
            types.TextContent(text=json.dumps(data, ensure_ascii=False, separators=(",", ":")))
        ],
        structured_content=data,
        _meta=metadata,
    )


def _candidate(hit: PublishedToolSearchHit) -> dict[str, Any]:
    tool = hit.tool
    return {
        "name": tool.canonical_name,
        "title": tool.display_name,
        "description": tool.description,
        "namespace": tool.namespace,
        "owner": tool.owner,
        "tags": list(tool.tags),
        "version": tool.version,
        "sideEffect": tool.side_effect.value,
        "inputSchema": dict(tool.input_schema),
        "outputSchema": dict(tool.output_schema) if tool.output_schema is not None else None,
        "toolId": tool.tool_id,
        "toolVersionId": tool.tool_version_id,
        "rank": hit.rank,
    }
