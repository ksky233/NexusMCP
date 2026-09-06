"""Toolset Aggregate、Grant 与派生健康度。"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum

from nexusmcp.shared.digests import canonical_json_digest

_TOOLSET_SLUG = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
_ALL_PUBLISHED_MEMBERSHIP_DIGEST = canonical_json_digest(
    {"kind": "all_published", "rule_version": 1}
)


class ToolsetKind(StrEnum):
    EXPLICIT = "explicit"
    ALL_PUBLISHED = "all_published"


class ToolsetDiscoveryMode(StrEnum):
    DIRECT = "direct"
    SEARCH_FIRST = "search_first"


class ToolsetStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    DISABLED = "disabled"


class ToolsetHealth(StrEnum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


class ToolsetMemberAvailability(StrEnum):
    AVAILABLE = "available"
    TOOL_DISABLED = "tool_disabled"
    NO_PUBLISHED_VERSION = "no_published_version"


@dataclass(frozen=True, slots=True)
class ToolsetMember:
    tenant_id: str
    toolset_id: str
    tool_id: str
    added_by: str
    added_at: datetime

    def __post_init__(self) -> None:
        _require_non_blank("member tenant id", self.tenant_id)
        _require_non_blank("member toolset id", self.toolset_id)
        _require_non_blank("member tool id", self.tool_id)
        _require_non_blank("member actor id", self.added_by)
        _require_aware("member added_at", self.added_at)


@dataclass(frozen=True, slots=True)
class ToolsetAccessGrant:
    tenant_id: str
    toolset_id: str
    principal_id: str
    granted_by: str
    granted_at: datetime

    def __post_init__(self) -> None:
        _require_non_blank("grant tenant id", self.tenant_id)
        _require_non_blank("grant toolset id", self.toolset_id)
        _require_non_blank("grant principal id", self.principal_id)
        _require_non_blank("grant actor id", self.granted_by)
        _require_aware("grant granted_at", self.granted_at)


@dataclass(frozen=True, slots=True)
class Toolset:
    """稳定 Endpoint 身份与当前 Member/Grant 集合组成一个 Aggregate。"""

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
    created_by: str
    created_at: datetime
    updated_at: datetime
    members: tuple[ToolsetMember, ...] = ()
    grants: tuple[ToolsetAccessGrant, ...] = ()

    def __post_init__(self) -> None:
        _require_non_blank("toolset id", self.id)
        _require_non_blank("toolset tenant id", self.tenant_id)
        _require_non_blank("toolset name", self.name)
        _require_non_blank("toolset creator", self.created_by)
        if len(self.slug) > 64 or _TOOLSET_SLUG.fullmatch(self.slug) is None:
            raise ValueError("toolset slug must use lowercase kebab-case")
        if len(self.name) > 128:
            raise ValueError("toolset name must not exceed 128 characters")
        if self.revision <= 0:
            raise ValueError("toolset revision must be positive")
        _require_digest("toolset membership digest", self.membership_digest)
        _require_aware("toolset created_at", self.created_at)
        _require_aware("toolset updated_at", self.updated_at)
        if self.updated_at < self.created_at:
            raise ValueError("toolset updated_at must not precede created_at")
        if self.kind is ToolsetKind.ALL_PUBLISHED and self.slug != "all-published":
            raise ValueError("system all_published toolset must use reserved slug")
        if self.kind is ToolsetKind.ALL_PUBLISHED and self.members:
            raise ValueError("all_published toolset must not contain explicit members")
        if (
            self.kind is ToolsetKind.EXPLICIT
            and self.status is ToolsetStatus.ACTIVE
            and not self.members
        ):
            raise ValueError("active explicit toolset must contain at least one member")
        _validate_members(self)
        _validate_grants(self)
        if self.membership_digest != calculate_membership_digest(self.kind, self.tool_ids):
            raise ValueError("toolset membership digest did not match members")

    @classmethod
    def create_explicit(
        cls,
        *,
        toolset_id: str,
        tenant_id: str,
        slug: str,
        name: str,
        description: str | None,
        created_by: str,
        created_at: datetime,
        discovery_mode: ToolsetDiscoveryMode = ToolsetDiscoveryMode.DIRECT,
    ) -> Toolset:
        return cls(
            id=toolset_id,
            tenant_id=tenant_id,
            slug=slug,
            name=name,
            description=description,
            kind=ToolsetKind.EXPLICIT,
            discovery_mode=discovery_mode,
            status=ToolsetStatus.DRAFT,
            revision=1,
            membership_digest=calculate_membership_digest(ToolsetKind.EXPLICIT, ()),
            created_by=created_by,
            created_at=created_at,
            updated_at=created_at,
        )

    @classmethod
    def create_all_published(
        cls,
        *,
        toolset_id: str,
        tenant_id: str,
        created_by: str,
        created_at: datetime,
    ) -> Toolset:
        return cls(
            id=toolset_id,
            tenant_id=tenant_id,
            slug="all-published",
            name="All Published Tools",
            description="System-managed view of all current published tools.",
            kind=ToolsetKind.ALL_PUBLISHED,
            discovery_mode=ToolsetDiscoveryMode.SEARCH_FIRST,
            status=ToolsetStatus.ACTIVE,
            revision=1,
            membership_digest=_ALL_PUBLISHED_MEMBERSHIP_DIGEST,
            created_by=created_by,
            created_at=created_at,
            updated_at=created_at,
        )

    @property
    def tool_ids(self) -> tuple[str, ...]:
        return tuple(member.tool_id for member in self.members)

    @property
    def principal_ids(self) -> tuple[str, ...]:
        return tuple(grant.principal_id for grant in self.grants)

    def update_profile(
        self,
        *,
        expected_revision: int,
        name: str,
        description: str | None,
        discovery_mode: ToolsetDiscoveryMode,
        updated_at: datetime,
    ) -> Toolset:
        self._require_revision(expected_revision)
        if self.kind is ToolsetKind.ALL_PUBLISHED and (
            self.name != name or self.description != description
        ):
            raise ValueError("system all_published toolset identity is immutable")
        if (
            self.name == name
            and self.description == description
            and self.discovery_mode is discovery_mode
        ):
            return self
        self._require_mutation_time(updated_at)
        return replace(
            self,
            name=name,
            description=description,
            discovery_mode=discovery_mode,
            revision=self.revision + 1,
            updated_at=updated_at,
        )

    def replace_members(
        self,
        *,
        expected_revision: int,
        tool_ids: Iterable[str],
        actor_id: str,
        occurred_at: datetime,
    ) -> Toolset:
        self._require_revision(expected_revision)
        if self.kind is ToolsetKind.ALL_PUBLISHED:
            raise ValueError("all_published toolset does not accept explicit members")
        normalized = _normalized_ids("tool id", tool_ids)
        if self.status is ToolsetStatus.ACTIVE and not normalized:
            raise ValueError("active explicit toolset must contain at least one member")
        if normalized == self.tool_ids:
            return self
        self._require_mutation_time(occurred_at)
        existing = {member.tool_id: member for member in self.members}
        members = tuple(
            existing.get(tool_id)
            or ToolsetMember(
                tenant_id=self.tenant_id,
                toolset_id=self.id,
                tool_id=tool_id,
                added_by=actor_id,
                added_at=occurred_at,
            )
            for tool_id in normalized
        )
        return replace(
            self,
            members=members,
            membership_digest=calculate_membership_digest(self.kind, normalized),
            revision=self.revision + 1,
            updated_at=occurred_at,
        )

    def replace_grants(
        self,
        *,
        expected_revision: int,
        principal_ids: Iterable[str],
        actor_id: str,
        occurred_at: datetime,
    ) -> Toolset:
        self._require_revision(expected_revision)
        normalized = _normalized_ids("principal id", principal_ids)
        if normalized == self.principal_ids:
            return self
        self._require_mutation_time(occurred_at)
        existing = {grant.principal_id: grant for grant in self.grants}
        grants = tuple(
            existing.get(principal_id)
            or ToolsetAccessGrant(
                tenant_id=self.tenant_id,
                toolset_id=self.id,
                principal_id=principal_id,
                granted_by=actor_id,
                granted_at=occurred_at,
            )
            for principal_id in normalized
        )
        return replace(
            self,
            grants=grants,
            revision=self.revision + 1,
            updated_at=occurred_at,
        )

    def activate(self, *, expected_revision: int, activated_at: datetime) -> Toolset:
        self._require_revision(expected_revision)
        if self.status is ToolsetStatus.ACTIVE:
            return self
        if self.kind is ToolsetKind.EXPLICIT and not self.members:
            raise ValueError("explicit toolset must contain members before activation")
        self._require_mutation_time(activated_at)
        return replace(
            self,
            status=ToolsetStatus.ACTIVE,
            revision=self.revision + 1,
            updated_at=activated_at,
        )

    def disable(self, *, expected_revision: int, disabled_at: datetime) -> Toolset:
        self._require_revision(expected_revision)
        if self.status is ToolsetStatus.DISABLED:
            return self
        if self.kind is ToolsetKind.ALL_PUBLISHED:
            raise ValueError("system all_published toolset cannot be disabled")
        self._require_mutation_time(disabled_at)
        return replace(
            self,
            status=ToolsetStatus.DISABLED,
            revision=self.revision + 1,
            updated_at=disabled_at,
        )

    def _require_revision(self, expected_revision: int) -> None:
        if expected_revision != self.revision:
            raise ValueError("toolset revision conflict")

    def _require_mutation_time(self, occurred_at: datetime) -> None:
        _require_aware("toolset mutation time", occurred_at)
        if occurred_at < self.updated_at:
            raise ValueError("toolset mutation time must not precede updated_at")


def calculate_membership_digest(kind: ToolsetKind, tool_ids: Iterable[str]) -> str:
    normalized = _normalized_ids("tool id", tool_ids)
    if kind is ToolsetKind.ALL_PUBLISHED:
        if normalized:
            raise ValueError("all_published membership digest does not accept tool ids")
        return _ALL_PUBLISHED_MEMBERSHIP_DIGEST
    return canonical_json_digest({"kind": kind.value, "tool_ids": list(normalized)})


def derive_toolset_health(
    availabilities: Mapping[str, ToolsetMemberAvailability],
) -> ToolsetHealth:
    if not availabilities:
        return ToolsetHealth.UNAVAILABLE
    available_count = sum(
        availability is ToolsetMemberAvailability.AVAILABLE
        for availability in availabilities.values()
    )
    if available_count == len(availabilities):
        return ToolsetHealth.HEALTHY
    if available_count == 0:
        return ToolsetHealth.UNAVAILABLE
    return ToolsetHealth.DEGRADED


def _validate_members(toolset: Toolset) -> None:
    tool_ids: set[str] = set()
    for member in toolset.members:
        if member.tenant_id != toolset.tenant_id or member.toolset_id != toolset.id:
            raise ValueError("toolset member crossed aggregate tenant or identity boundary")
        if member.tool_id in tool_ids:
            raise ValueError("toolset member tool id must be unique")
        tool_ids.add(member.tool_id)


def _validate_grants(toolset: Toolset) -> None:
    principal_ids: set[str] = set()
    for grant in toolset.grants:
        if grant.tenant_id != toolset.tenant_id or grant.toolset_id != toolset.id:
            raise ValueError("toolset grant crossed aggregate tenant or identity boundary")
        if grant.principal_id in principal_ids:
            raise ValueError("toolset grant principal id must be unique")
        principal_ids.add(grant.principal_id)


def _normalized_ids(field_name: str, values: Iterable[str]) -> tuple[str, ...]:
    normalized: set[str] = set()
    for value in values:
        _require_non_blank(field_name, value)
        normalized.add(value)
    return tuple(sorted(normalized))


def _require_non_blank(field_name: str, value: str) -> None:
    if not value.strip():
        raise ValueError(f"{field_name} must not be blank")


def _require_digest(field_name: str, value: str) -> None:
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError(f"{field_name} must be a lowercase sha256 digest")


def _require_aware(field_name: str, value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
