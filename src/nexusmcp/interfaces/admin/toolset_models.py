"""Toolset Admin API 的稳定 Request/Response Contract。"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from nexusmcp.interfaces.admin.query_models import PageMetadata
from nexusmcp.modules.toolsets.domain import (
    ToolsetDiscoveryMode,
    ToolsetHealth,
    ToolsetKind,
    ToolsetMemberAvailability,
    ToolsetStatus,
)
from nexusmcp.modules.toolsets.use_cases import ToolsetMemberProfile, ToolsetProfile


class ToolsetApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CreateToolsetRequest(ToolsetApiModel):
    slug: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    name: str = Field(min_length=1, max_length=128)
    description: str | None = None
    discovery_mode: ToolsetDiscoveryMode = ToolsetDiscoveryMode.DIRECT


class UpdateToolsetRequest(ToolsetApiModel):
    expected_revision: int = Field(ge=1)
    name: str = Field(min_length=1, max_length=128)
    description: str | None = None
    discovery_mode: ToolsetDiscoveryMode


class ReplaceToolsetMembersRequest(ToolsetApiModel):
    expected_revision: int = Field(ge=1)
    tool_ids: list[str]


class ReplaceToolsetAccessGrantsRequest(ToolsetApiModel):
    expected_revision: int = Field(ge=1)
    principal_ids: list[str]


class ChangeToolsetStatusRequest(ToolsetApiModel):
    expected_revision: int = Field(ge=1)


class ToolsetMemberResponse(ToolsetApiModel):
    tool_id: str
    canonical_name: str | None
    description: str | None
    availability: ToolsetMemberAvailability
    published_tool_version_id: str | None
    serialized_schema_size: int

    @classmethod
    def from_profile(cls, profile: ToolsetMemberProfile) -> ToolsetMemberResponse:
        return cls.model_validate(profile, from_attributes=True)


class ToolsetResponse(ToolsetApiModel):
    id: str
    tenant_id: str
    slug: str
    name: str
    description: str | None
    kind: ToolsetKind
    discovery_mode: ToolsetDiscoveryMode
    status: ToolsetStatus
    revision: int
    membership_digest: str
    endpoint_path: str
    health: ToolsetHealth
    tool_count: int
    available_tool_count: int
    serialized_schema_size: int
    grant_count: int
    principal_ids: list[str]
    members: list[ToolsetMemberResponse]
    created_by: str
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_profile(cls, profile: ToolsetProfile) -> ToolsetResponse:
        return cls(
            id=profile.id,
            tenant_id=profile.tenant_id,
            slug=profile.slug,
            name=profile.name,
            description=profile.description,
            kind=profile.kind,
            discovery_mode=profile.discovery_mode,
            status=profile.status,
            revision=profile.revision,
            membership_digest=profile.membership_digest,
            endpoint_path=profile.endpoint_path,
            health=profile.health,
            tool_count=profile.tool_count,
            available_tool_count=profile.available_tool_count,
            serialized_schema_size=profile.serialized_schema_size,
            grant_count=len(profile.principal_ids),
            principal_ids=list(profile.principal_ids),
            members=[ToolsetMemberResponse.from_profile(item) for item in profile.members],
            created_by=profile.created_by,
            created_at=profile.created_at,
            updated_at=profile.updated_at,
        )


class ToolsetPageResponse(ToolsetApiModel):
    items: list[ToolsetResponse]
    page: PageMetadata
