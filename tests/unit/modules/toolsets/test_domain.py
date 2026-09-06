"""Toolset Aggregate、Revision 与派生 Health 不变量。"""

from datetime import UTC, datetime, timedelta

import pytest

from nexusmcp.modules.toolsets.domain import (
    Toolset,
    ToolsetDiscoveryMode,
    ToolsetHealth,
    ToolsetKind,
    ToolsetMemberAvailability,
    ToolsetStatus,
    derive_toolset_health,
)

NOW = datetime(2026, 9, 6, tzinfo=UTC)
LATER = NOW + timedelta(minutes=1)


def explicit_toolset() -> Toolset:
    return Toolset.create_explicit(
        toolset_id="toolset-operations",
        tenant_id="tenant-a",
        slug="risk-operations",
        name="Risk Operations",
        description="Risk and incident response tools.",
        created_by="admin-a",
        created_at=NOW,
    )


def test_create_explicit_toolset_has_draft_direct_empty_baseline() -> None:
    toolset = explicit_toolset()

    assert toolset.kind is ToolsetKind.EXPLICIT
    assert toolset.discovery_mode is ToolsetDiscoveryMode.DIRECT
    assert toolset.status is ToolsetStatus.DRAFT
    assert toolset.revision == 1
    assert toolset.tool_ids == ()
    assert len(toolset.membership_digest) == 64


@pytest.mark.parametrize("slug", ["Risk", "risk_operations", "-risk", "risk-", "risk--ops"])
def test_toolset_slug_requires_lowercase_kebab_case(slug: str) -> None:
    with pytest.raises(ValueError, match="kebab-case"):
        Toolset.create_explicit(
            toolset_id="toolset-1",
            tenant_id="tenant-a",
            slug=slug,
            name="Risk",
            description=None,
            created_by="admin-a",
            created_at=NOW,
        )


def test_replace_members_is_canonical_idempotent_and_preserves_existing_metadata() -> None:
    toolset = explicit_toolset().replace_members(
        expected_revision=1,
        tool_ids=("tool-risk", "tool-ops", "tool-risk"),
        actor_id="admin-a",
        occurred_at=NOW,
    )

    assert toolset.tool_ids == ("tool-ops", "tool-risk")
    assert toolset.revision == 2
    assert {member.added_by for member in toolset.members} == {"admin-a"}

    unchanged = toolset.replace_members(
        expected_revision=2,
        tool_ids=("tool-risk", "tool-ops"),
        actor_id="admin-b",
        occurred_at=LATER,
    )
    assert unchanged is toolset

    changed = toolset.replace_members(
        expected_revision=2,
        tool_ids=("tool-ops", "tool-new"),
        actor_id="admin-b",
        occurred_at=LATER,
    )
    members = {member.tool_id: member for member in changed.members}
    assert changed.revision == 3
    assert members["tool-ops"].added_by == "admin-a"
    assert members["tool-new"].added_by == "admin-b"


def test_replace_grants_supports_many_to_many_and_is_idempotent() -> None:
    toolset = explicit_toolset().replace_grants(
        expected_revision=1,
        principal_ids=("risk-agent", "operations-agent", "risk-agent"),
        actor_id="admin-a",
        occurred_at=NOW,
    )

    assert toolset.principal_ids == ("operations-agent", "risk-agent")
    assert toolset.revision == 2
    assert (
        toolset.replace_grants(
            expected_revision=2,
            principal_ids=("risk-agent", "operations-agent"),
            actor_id="admin-b",
            occurred_at=LATER,
        )
        is toolset
    )


def test_revision_conflict_precedes_aggregate_mutation() -> None:
    with pytest.raises(ValueError, match="revision conflict"):
        explicit_toolset().replace_members(
            expected_revision=2,
            tool_ids=("tool-1",),
            actor_id="admin-a",
            occurred_at=NOW,
        )


def test_explicit_toolset_requires_members_before_activation() -> None:
    with pytest.raises(ValueError, match="contain members"):
        explicit_toolset().activate(expected_revision=1, activated_at=LATER)

    with_member = explicit_toolset().replace_members(
        expected_revision=1,
        tool_ids=("tool-1",),
        actor_id="admin-a",
        occurred_at=NOW,
    )
    active = with_member.activate(expected_revision=2, activated_at=LATER)
    disabled = active.disable(expected_revision=3, disabled_at=LATER)

    assert active.status is ToolsetStatus.ACTIVE
    assert active.revision == 3
    assert disabled.status is ToolsetStatus.DISABLED
    assert disabled.revision == 4


def test_all_published_is_active_search_first_and_rejects_explicit_members() -> None:
    toolset = Toolset.create_all_published(
        toolset_id="toolset-all",
        tenant_id="tenant-a",
        created_by="system",
        created_at=NOW,
    )

    assert toolset.kind is ToolsetKind.ALL_PUBLISHED
    assert toolset.slug == "all-published"
    assert toolset.status is ToolsetStatus.ACTIVE
    assert toolset.discovery_mode is ToolsetDiscoveryMode.SEARCH_FIRST
    direct = toolset.update_profile(
        expected_revision=1,
        name=toolset.name,
        description=toolset.description,
        discovery_mode=ToolsetDiscoveryMode.DIRECT,
        updated_at=LATER,
    )
    assert direct.discovery_mode is ToolsetDiscoveryMode.DIRECT
    assert direct.revision == 2
    with pytest.raises(ValueError, match="identity is immutable"):
        toolset.update_profile(
            expected_revision=1,
            name="Renamed system toolset",
            description=toolset.description,
            discovery_mode=toolset.discovery_mode,
            updated_at=LATER,
        )
    with pytest.raises(ValueError, match="does not accept explicit members"):
        toolset.replace_members(
            expected_revision=1,
            tool_ids=("tool-1",),
            actor_id="admin-a",
            occurred_at=LATER,
        )
    with pytest.raises(ValueError, match="cannot be disabled"):
        toolset.disable(expected_revision=1, disabled_at=LATER)


def test_mutation_time_cannot_move_aggregate_clock_backwards() -> None:
    toolset = explicit_toolset().replace_members(
        expected_revision=1,
        tool_ids=("tool-1",),
        actor_id="admin-a",
        occurred_at=LATER,
    )

    with pytest.raises(ValueError, match="must not precede updated_at"):
        toolset.replace_grants(
            expected_revision=2,
            principal_ids=("agent-a",),
            actor_id="admin-a",
            occurred_at=NOW,
        )


def test_system_health_is_derived_from_current_member_availability() -> None:
    assert derive_toolset_health({}) is ToolsetHealth.UNAVAILABLE
    assert (
        derive_toolset_health({"tool-1": ToolsetMemberAvailability.AVAILABLE})
        is ToolsetHealth.HEALTHY
    )
    assert (
        derive_toolset_health(
            {
                "tool-1": ToolsetMemberAvailability.AVAILABLE,
                "tool-2": ToolsetMemberAvailability.TOOL_DISABLED,
            }
        )
        is ToolsetHealth.DEGRADED
    )
    assert (
        derive_toolset_health(
            {
                "tool-1": ToolsetMemberAvailability.TOOL_DISABLED,
                "tool-2": ToolsetMemberAvailability.NO_PUBLISHED_VERSION,
            }
        )
        is ToolsetHealth.UNAVAILABLE
    )
