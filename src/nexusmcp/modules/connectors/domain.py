"""Connectors 上下文的 Tool 执行绑定模型。"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
from typing import Any


class ToolBindingType(StrEnum):
    HTTP = "http"
    REMOTE_MCP = "remote_mcp"


class ToolBindingStatus(StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"
    DISABLED = "disabled"


@dataclass(frozen=True, slots=True)
class ToolBinding:
    """将一个 ToolVersion 精确映射到一个非敏感执行配置。"""

    id: str
    tenant_id: str
    tool_version_id: str
    upstream_service_id: str
    imported_operation_id: str | None
    binding_type: ToolBindingType
    binding_config: Mapping[str, Any]
    binding_digest: str
    status: ToolBindingStatus
    created_at: datetime
    published_at: datetime | None = None

    def __post_init__(self) -> None:
        for field_name, value in (
            ("tool binding id", self.id),
            ("tenant id", self.tenant_id),
            ("tool version id", self.tool_version_id),
            ("upstream service id", self.upstream_service_id),
            ("binding digest", self.binding_digest),
        ):
            if not value.strip():
                raise ValueError(f"{field_name} must not be blank")
        if self.status is ToolBindingStatus.PUBLISHED and self.published_at is None:
            raise ValueError("published tool binding must have published_at")

    def publish(self, published_at: datetime) -> ToolBinding:
        """只允许 Draft Binding 与 ToolVersion 在同一事务中进入 Published。"""

        if self.status is not ToolBindingStatus.DRAFT:
            raise ValueError("only draft tool binding can be published")
        return replace(
            self,
            status=ToolBindingStatus.PUBLISHED,
            published_at=published_at,
        )

    def disable(self) -> ToolBinding:
        """停用已发布 Binding；历史配置保持不变。"""

        if self.status is not ToolBindingStatus.PUBLISHED:
            raise ValueError("only published tool binding can be disabled")
        return replace(self, status=ToolBindingStatus.DISABLED)
