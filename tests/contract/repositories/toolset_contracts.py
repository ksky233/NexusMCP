"""Toolset Repository/UoW Adapter 共享 Contract。"""

from dataclasses import replace
from datetime import UTC, datetime

import pytest

from nexusmcp.modules.toolsets.domain import Toolset
from nexusmcp.modules.toolsets.ports import ToolsetRepository, ToolsetUnitOfWork

TENANT_A_ID = "00000000-0000-0000-0000-00000000000a"
TENANT_B_ID = "00000000-0000-0000-0000-00000000000b"
MEMBER_TOOL_ID = "00000000-0000-0000-0000-000000000101"
NOW = datetime(2026, 9, 6, tzinfo=UTC)


def make_toolset(
    *,
    toolset_id: str = "00000000-0000-0000-0000-000000000501",
    tenant_id: str = TENANT_A_ID,
    slug: str = "operations",
    active: bool = False,
    principal_ids: tuple[str, ...] = (),
) -> Toolset:
    toolset = Toolset.create_explicit(
        toolset_id=toolset_id,
        tenant_id=tenant_id,
        slug=slug,
        name=slug.replace("-", " ").title(),
        description=f"{slug} tools",
        created_by="admin-a",
        created_at=NOW,
    ).replace_members(
        expected_revision=1,
        tool_ids=(MEMBER_TOOL_ID,),
        actor_id="admin-a",
        occurred_at=NOW,
    )
    if principal_ids:
        toolset = toolset.replace_grants(
            expected_revision=toolset.revision,
            principal_ids=principal_ids,
            actor_id="admin-a",
            occurred_at=NOW,
        )
    return (
        toolset.activate(expected_revision=toolset.revision, activated_at=NOW)
        if active
        else toolset
    )


class ToolsetRepositoryContract:
    @pytest.mark.asyncio
    async def test_stores_updates_and_tenant_scopes_toolset(
        self,
        empty_toolsets: ToolsetRepository,
    ) -> None:
        toolset = make_toolset()
        await empty_toolsets.add(TENANT_A_ID, toolset)

        assert await empty_toolsets.get_by_id(TENANT_A_ID, toolset.id) == toolset
        assert await empty_toolsets.get_for_update(TENANT_A_ID, toolset.id) == toolset
        assert await empty_toolsets.get_by_slug(TENANT_A_ID, toolset.slug) == toolset
        assert await empty_toolsets.get_by_id(TENANT_B_ID, toolset.id) is None

        updated = toolset.update_profile(
            expected_revision=toolset.revision,
            name="Platform Operations",
            description=toolset.description,
            discovery_mode=toolset.discovery_mode,
            updated_at=NOW,
        )
        await empty_toolsets.save(TENANT_A_ID, updated)
        persisted = await empty_toolsets.get_by_id(TENANT_A_ID, toolset.id)
        assert persisted == updated, (persisted, updated)

        # 相同 Aggregate 重放是幂等操作；任何真实变更必须严格推进一个 Revision。
        await empty_toolsets.save(TENANT_A_ID, updated)
        with pytest.raises(ValueError, match="revision transition"):
            await empty_toolsets.save(
                TENANT_A_ID,
                replace(updated, name="Bypassed Domain"),
            )
        with pytest.raises(ValueError, match="revision transition"):
            await empty_toolsets.save(
                TENANT_A_ID,
                replace(updated, name="Skipped Revision", revision=updated.revision + 2),
            )

        with pytest.raises(ValueError, match="stable identity"):
            await empty_toolsets.save(TENANT_A_ID, replace(updated, slug="renamed"))

    @pytest.mark.asyncio
    async def test_lists_only_active_toolsets_granted_to_principal(
        self,
        empty_toolsets: ToolsetRepository,
    ) -> None:
        operations = make_toolset(active=True, principal_ids=("agent-a",))
        risk = make_toolset(
            toolset_id="00000000-0000-0000-0000-000000000502",
            slug="risk",
            active=True,
            principal_ids=("agent-a", "agent-b"),
        )
        draft = make_toolset(
            toolset_id="00000000-0000-0000-0000-000000000503",
            slug="draft-tools",
            principal_ids=("agent-a",),
        )
        for toolset in (operations, risk, draft):
            await empty_toolsets.add(TENANT_A_ID, toolset)

        assert await empty_toolsets.list_granted_active(TENANT_A_ID, "agent-a") == (
            operations,
            risk,
        )
        assert await empty_toolsets.list_granted_active(TENANT_A_ID, "agent-b") == (risk,)
        assert await empty_toolsets.list_granted_active(TENANT_B_ID, "agent-a") == ()

    @pytest.mark.asyncio
    async def test_rejects_duplicate_slug(
        self,
        empty_toolsets: ToolsetRepository,
    ) -> None:
        await empty_toolsets.add(TENANT_A_ID, make_toolset())
        with pytest.raises(ValueError, match="slug|uniqueness"):
            await empty_toolsets.add(
                TENANT_A_ID,
                make_toolset(
                    toolset_id="00000000-0000-0000-0000-000000000599",
                ),
            )

    @pytest.mark.asyncio
    async def test_rejects_duplicate_system_toolset(
        self,
        empty_toolsets: ToolsetRepository,
    ) -> None:
        system = Toolset.create_all_published(
            toolset_id="00000000-0000-0000-0000-000000000510",
            tenant_id=TENANT_A_ID,
            created_by="system",
            created_at=NOW,
        )
        await empty_toolsets.add(TENANT_A_ID, system)
        with pytest.raises(ValueError, match="uniqueness|slug|all_published"):
            await empty_toolsets.add(
                TENANT_A_ID,
                Toolset.create_all_published(
                    toolset_id="00000000-0000-0000-0000-000000000511",
                    tenant_id=TENANT_A_ID,
                    created_by="system",
                    created_at=NOW,
                ),
            )

    @pytest.mark.asyncio
    async def test_rejects_cross_tenant_entity(
        self,
        empty_toolsets: ToolsetRepository,
    ) -> None:
        with pytest.raises(ValueError, match="tenant"):
            await empty_toolsets.add(TENANT_B_ID, make_toolset())


class ToolsetUnitOfWorkContract:
    @pytest.mark.asyncio
    async def test_commit_persists_aggregate(
        self,
        unit_of_work_bundle: tuple[ToolsetUnitOfWork, ToolsetRepository],
    ) -> None:
        unit_of_work, committed_toolsets = unit_of_work_bundle
        toolset = make_toolset()

        async with unit_of_work:
            await unit_of_work.toolsets.add(TENANT_A_ID, toolset)
            await unit_of_work.commit()

        assert await committed_toolsets.get_by_id(TENANT_A_ID, toolset.id) == toolset

    @pytest.mark.asyncio
    async def test_exit_without_commit_and_explicit_rollback_discard_changes(
        self,
        unit_of_work_bundle: tuple[ToolsetUnitOfWork, ToolsetRepository],
    ) -> None:
        unit_of_work, committed_toolsets = unit_of_work_bundle
        toolset = make_toolset()

        async with unit_of_work:
            await unit_of_work.toolsets.add(TENANT_A_ID, toolset)
        assert await committed_toolsets.get_by_id(TENANT_A_ID, toolset.id) is None

        async with unit_of_work:
            await unit_of_work.toolsets.add(TENANT_A_ID, toolset)
            await unit_of_work.rollback()
            await unit_of_work.commit()
        assert await committed_toolsets.get_by_id(TENANT_A_ID, toolset.id) is None
