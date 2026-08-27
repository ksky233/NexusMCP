"""Published ToolVersion 到 Canonical Tool Search Document 的确定性转换。"""

import hashlib
from collections.abc import Mapping
from typing import Any

from nexusmcp.modules.catalog.domain import PublishedTool
from nexusmcp.modules.tool_search.domain import ToolSearchDocument


class ToolSearchDocumentBuilder:
    def build(self, tool: PublishedTool) -> ToolSearchDocument:
        lines = (
            f"Canonical Name: {tool.canonical_name}",
            f"Display Name: {_normalize_text(tool.display_name)}",
            f"Namespace: {tool.namespace}",
            f"Description: {_normalize_text(tool.description)}",
            f"Tags: {', '.join(sorted(tool.tags)) or 'none'}",
            f"Side Effect: {tool.side_effect.value}",
            f"Inputs: {', '.join(_input_field_summaries(tool.input_schema)) or 'none'}",
            f"Owner: {_normalize_text(tool.owner or 'unknown')}",
        )
        content = "\n".join(lines)
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        return ToolSearchDocument(
            tenant_id=tool.tenant_id,
            tool_id=tool.tool_id,
            tool_version_id=tool.tool_version_id,
            canonical_name=tool.canonical_name,
            content=content,
            source_digest=digest,
        )


def _input_field_summaries(schema: Mapping[str, Any]) -> tuple[str, ...]:
    required = {str(name) for name in schema.get("required", ()) if isinstance(name, str)}
    properties = schema.get("properties")
    if not isinstance(properties, Mapping):
        return ()
    fields: list[str] = []
    for name in sorted(str(key) for key in properties):
        value = properties.get(name)
        if not isinstance(value, Mapping):
            continue
        _collect_field(fields, name, value, required=name in required, depth=0)
    return tuple(fields)


def _collect_field(
    fields: list[str],
    path: str,
    schema: Mapping[str, Any],
    *,
    required: bool,
    depth: int,
) -> None:
    nested = schema.get("properties")
    if isinstance(nested, Mapping) and nested and depth < 3:
        nested_required = {
            str(name) for name in schema.get("required", ()) if isinstance(name, str)
        }
        for name in sorted(str(key) for key in nested):
            value = nested.get(name)
            if isinstance(value, Mapping):
                _collect_field(
                    fields,
                    f"{path}.{name}",
                    value,
                    required=name in nested_required,
                    depth=depth + 1,
                )
        return
    field_type = schema.get("type", "unknown")
    if isinstance(field_type, list):
        field_type_text = "|".join(sorted(str(value) for value in field_type))
    else:
        field_type_text = str(field_type)
    description = schema.get("description")
    suffix = "required" if required else "optional"
    summary = f"{path} ({field_type_text}, {suffix})"
    if isinstance(description, str) and description.strip():
        summary += f": {_normalize_text(description)}"
    fields.append(summary)


def _normalize_text(value: str) -> str:
    return " ".join(value.split())
