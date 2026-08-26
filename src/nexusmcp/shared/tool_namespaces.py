"""系统保留 Tool Namespace 契约。"""

RESERVED_TOOL_NAMESPACES = frozenset({"nexus"})


def is_reserved_tool_namespace(namespace: str) -> bool:
    return namespace in RESERVED_TOOL_NAMESPACES
