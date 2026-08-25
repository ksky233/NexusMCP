"""Tool Catalog 的稳定身份、版本化契约与发布只读投影。"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
from typing import Any

from nexusmcp.shared.request_context import ANONYMOUS_PRINCIPAL_ID


class ToolStatus(StrEnum):
    ACTIVE = "active"
    DISABLED = "disabled"


class ToolVersionStatus(StrEnum):
    DRAFT = "draft"
    REVIEW = "review"
    PUBLISHED = "published"
    RETIRED = "retired"


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
class Tool:
    """跨版本保持稳定的 Tool Identity。"""

    id: str
    tenant_id: str
    namespace: str
    canonical_name: str
    owner: str
    status: ToolStatus = ToolStatus.ACTIVE

    def __post_init__(self) -> None:
        _require_non_blank("tool id", self.id)
        _require_non_blank("tenant id", self.tenant_id)
        _require_non_blank("tool namespace", self.namespace)
        _require_non_blank("tool canonical name", self.canonical_name)
        _require_non_blank("tool owner", self.owner)
        if not self.canonical_name.startswith(f"{self.namespace}."):
            raise ValueError("tool canonical name must start with its namespace")


@dataclass(frozen=True, slots=True)
class ToolVersion:
    """属于稳定 Tool Identity 的版本化 Agent 契约。"""

    id: str
    tenant_id: str
    tool_id: str
    version: int
    display_name: str
    description: str
    input_schema: Mapping[str, Any]
    output_schema: Mapping[str, Any] | None
    schema_digest: str
    tags: tuple[str, ...]
    side_effect: ToolSideEffect
    visibility: ToolVisibility
    status: ToolVersionStatus
    created_by: str
    created_at: datetime
    reviewed_at: datetime | None = None
    published_at: datetime | None = None
    retired_at: datetime | None = None

    def __post_init__(self) -> None:
        _require_non_blank("tool version id", self.id)
        _require_non_blank("tenant id", self.tenant_id)
        _require_non_blank("tool id", self.tool_id)
        _require_non_blank("tool display name", self.display_name)
        _require_non_blank("schema digest", self.schema_digest)
        _require_non_blank("tool version creator", self.created_by)
        if self.version < 1:
            raise ValueError("tool version must be positive")
        _validate_input_schema(self.input_schema)
        _validate_lifecycle_timestamps(self)

    def submit_for_review(self, reviewed_at: datetime) -> ToolVersion:
        """将完整 Draft 提交 Review，拒绝跳过或重复生命周期步骤。"""

        if self.status is not ToolVersionStatus.DRAFT:
            raise ValueError("only draft tool version can be submitted for review")
        return replace(
            self,
            status=ToolVersionStatus.REVIEW,
            reviewed_at=reviewed_at,
        )

    def publish(self, published_at: datetime) -> ToolVersion:
        """将通过 Review 的版本发布，不允许直接发布 Draft。"""

        if self.status is not ToolVersionStatus.REVIEW:
            raise ValueError("only review tool version can be published")
        return replace(
            self,
            status=ToolVersionStatus.PUBLISHED,
            published_at=published_at,
        )

    def retire(self, retired_at: datetime) -> ToolVersion:
        """保留历史版本证据，同时将其移出 Published 状态。"""

        if self.status is not ToolVersionStatus.PUBLISHED:
            raise ValueError("only published tool version can be retired")
        return replace(
            self,
            status=ToolVersionStatus.RETIRED,
            retired_at=retired_at,
        )


@dataclass(frozen=True, slots=True)
class PublishedTool:
    """供发现链路读取的已发布 Tool 投影，不承担写模型职责。"""

    tool_id: str
    tool_version_id: str
    tenant_id: str
    canonical_name: str
    display_name: str
    description: str
    input_schema: Mapping[str, Any]
    output_schema: Mapping[str, Any] | None
    version: int
    visibility: ToolVisibility
    side_effect: ToolSideEffect
    schema_digest: str

    def __post_init__(self) -> None:
        _require_non_blank("tool id", self.tool_id)
        _require_non_blank("tool version id", self.tool_version_id)
        _require_non_blank("tenant id", self.tenant_id)
        _require_non_blank("tool canonical name", self.canonical_name)
        _require_non_blank("tool display name", self.display_name)
        _require_non_blank("schema digest", self.schema_digest)
        if self.version < 1:
            raise ValueError("tool version must be positive")
        _validate_input_schema(self.input_schema)

    def is_visible_to(self, principal_id: str) -> bool:
        """执行 S2 粗粒度发现规则；Restricted 在 S3 Policy 接入前默认拒绝。"""

        if self.visibility is ToolVisibility.PUBLIC:
            return True
        if self.visibility is ToolVisibility.AUTHENTICATED:
            return principal_id != ANONYMOUS_PRINCIPAL_ID
        return False


def _require_non_blank(field_name: str, value: str) -> None:
    if not value.strip():
        raise ValueError(f"{field_name} must not be blank")


def _validate_input_schema(input_schema: Mapping[str, Any]) -> None:
    if input_schema.get("type") != "object":
        raise ValueError("tool input schema root type must be object")


def _validate_lifecycle_timestamps(version: ToolVersion) -> None:
    if (
        version.status
        in (
            ToolVersionStatus.REVIEW,
            ToolVersionStatus.PUBLISHED,
            ToolVersionStatus.RETIRED,
        )
        and version.reviewed_at is None
    ):
        raise ValueError("review tool version must have reviewed_at")
    if (
        version.status
        in (
            ToolVersionStatus.PUBLISHED,
            ToolVersionStatus.RETIRED,
        )
        and version.published_at is None
    ):
        raise ValueError("published tool version must have published_at")
    if version.status is ToolVersionStatus.RETIRED and version.retired_at is None:
        raise ValueError("retired tool version must have retired_at")
