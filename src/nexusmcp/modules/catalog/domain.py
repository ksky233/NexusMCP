"""Tool Catalog 的 Entity、Value 与可见性不变量。"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from nexusmcp.shared.request_context import ANONYMOUS_PRINCIPAL_ID


class ToolStatus(StrEnum):
    DRAFT = "draft"
    REVIEW = "review"
    PUBLISHED = "published"
    DISABLED = "disabled"


class ToolVisibility(StrEnum):
    PUBLIC = "public"
    AUTHENTICATED = "authenticated"
    RESTRICTED = "restricted"


class ToolSideEffect(StrEnum):
    READ_ONLY = "read_only"
    IDEMPOTENT_WRITE = "idempotent_write"
    NON_IDEMPOTENT_WRITE = "non_idempotent_write"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    """向 MCP Client 暴露的版本化 Tool 契约。"""

    id: str
    tenant_id: str
    canonical_name: str
    display_name: str
    description: str
    input_schema: Mapping[str, Any]
    version: int = 1
    status: ToolStatus = ToolStatus.DRAFT
    visibility: ToolVisibility = ToolVisibility.RESTRICTED
    side_effect: ToolSideEffect = ToolSideEffect.UNKNOWN
    output_schema: Mapping[str, Any] | None = None
    allowed_principal_ids: frozenset[str] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise ValueError("tool id must not be blank")
        if not self.tenant_id.strip():
            raise ValueError("tenant id must not be blank")
        if not self.canonical_name.strip():
            raise ValueError("canonical name must not be blank")
        if self.version < 1:
            raise ValueError("tool version must be positive")
        if self.input_schema.get("type") != "object":
            raise ValueError("tool input schema root type must be object")
        if self.visibility is ToolVisibility.RESTRICTED and not self.allowed_principal_ids:
            raise ValueError("restricted tool must declare allowed principals")

    def is_visible_to(self, principal_id: str) -> bool:
        """应用 Catalog 生命周期和粗粒度可见性规则。"""

        if self.status is not ToolStatus.PUBLISHED:
            return False
        if self.visibility is ToolVisibility.PUBLIC:
            return True
        if self.visibility is ToolVisibility.AUTHENTICATED:
            return principal_id != ANONYMOUS_PRINCIPAL_ID
        return principal_id in self.allowed_principal_ids
