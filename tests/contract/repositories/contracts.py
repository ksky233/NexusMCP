"""Repository Adapter 共享的 Port Contract 与确定性 Domain Fixture。"""

from dataclasses import replace
from datetime import UTC, datetime

import pytest

from nexusmcp.modules.catalog.domain import (
    PublishedTool,
    Tool,
    ToolSideEffect,
    ToolStatus,
    ToolVersion,
    ToolVersionStatus,
    ToolVisibility,
)
from nexusmcp.modules.catalog.ports import CatalogUnitOfWork, ToolCatalogRepository
from nexusmcp.modules.connectors.domain import (
    ToolBinding,
    ToolBindingStatus,
    ToolBindingType,
)
from nexusmcp.modules.connectors.ports import ToolBindingRepository

TENANT_A_ID = "00000000-0000-0000-0000-00000000000a"
TENANT_B_ID = "00000000-0000-0000-0000-00000000000b"
TOOL_ID = "00000000-0000-0000-0000-000000000101"
VERSION_ID = "00000000-0000-0000-0000-000000000201"
PUBLISHED_VERSION_ID = "00000000-0000-0000-0000-000000000202"
BINDING_ID = "00000000-0000-0000-0000-000000000301"
UPSTREAM_ID = "00000000-0000-0000-0000-000000000401"
NOW = datetime(2026, 8, 25, tzinfo=UTC)


def make_tool(tenant_id: str = TENANT_A_ID) -> Tool:
    return Tool(
        id=TOOL_ID,
        tenant_id=tenant_id,
        namespace="directory",
        canonical_name="directory.get_employee",
        owner="people-platform",
    )


def make_version(
    tenant_id: str = TENANT_A_ID,
    status: ToolVersionStatus = ToolVersionStatus.DRAFT,
) -> ToolVersion:
    return ToolVersion(
        id=VERSION_ID,
        tenant_id=tenant_id,
        tool_id=TOOL_ID,
        version=1,
        display_name="Get employee",
        description="Get one employee by id.",
        input_schema={"type": "object", "properties": {}},
        output_schema=None,
        schema_digest="1" * 64,
        tags=("directory", "employee"),
        side_effect=ToolSideEffect.READ_ONLY,
        visibility=ToolVisibility.PUBLIC,
        status=status,
        created_by="import-reviewer",
        created_at=NOW,
        reviewed_at=(
            NOW
            if status
            in (
                ToolVersionStatus.REVIEW,
                ToolVersionStatus.PUBLISHED,
                ToolVersionStatus.RETIRED,
            )
            else None
        ),
        published_at=(
            NOW if status in (ToolVersionStatus.PUBLISHED, ToolVersionStatus.RETIRED) else None
        ),
        retired_at=NOW if status is ToolVersionStatus.RETIRED else None,
    )


def make_published_tool(tenant_id: str = TENANT_A_ID) -> PublishedTool:
    return PublishedTool(
        tool_id=TOOL_ID,
        tool_version_id=VERSION_ID,
        tenant_id=tenant_id,
        canonical_name="directory.get_employee",
        display_name="Get employee",
        description="Get one employee by id.",
        input_schema={"type": "object", "properties": {}},
        output_schema=None,
        version=1,
        visibility=ToolVisibility.PUBLIC,
        side_effect=ToolSideEffect.READ_ONLY,
        schema_digest="1" * 64,
        owner="people-platform",
        tags=("directory", "employee"),
    )


def make_binding(tenant_id: str = TENANT_A_ID) -> ToolBinding:
    return ToolBinding(
        id=BINDING_ID,
        tenant_id=tenant_id,
        tool_version_id=VERSION_ID,
        upstream_service_id=UPSTREAM_ID,
        imported_operation_id=None,
        binding_type=ToolBindingType.HTTP,
        binding_config={"method": "GET", "path_template": "/employees/{employee_id}"},
        binding_digest="2" * 64,
        status=ToolBindingStatus.DRAFT,
        created_at=NOW,
    )


class CatalogRepositoryContract:
    """所有 ToolCatalogRepository Adapter 必须通过的可观察行为。"""

    @pytest.mark.asyncio
    async def test_stores_updates_and_tenant_scopes_tool_identity(
        self,
        empty_catalog: ToolCatalogRepository,
    ) -> None:
        tool = make_tool()

        await empty_catalog.add_tool(TENANT_A_ID, tool)

        assert await empty_catalog.get_tool_by_id(TENANT_A_ID, tool.id) == tool
        assert await empty_catalog.get_tool_by_name(TENANT_A_ID, tool.canonical_name) == tool
        assert (
            await empty_catalog.get_tool_by_name_for_update(
                TENANT_A_ID,
                tool.canonical_name,
            )
            == tool
        )
        assert await empty_catalog.get_tool_for_update(TENANT_A_ID, tool.id) == tool
        assert await empty_catalog.get_tool_by_id(TENANT_B_ID, tool.id) is None

        disabled = replace(tool, status=ToolStatus.DISABLED)
        await empty_catalog.save_tool(TENANT_A_ID, disabled)
        assert await empty_catalog.get_tool_by_id(TENANT_A_ID, tool.id) == disabled

    @pytest.mark.asyncio
    async def test_stores_versions_and_finds_only_the_published_version(
        self,
        empty_catalog: ToolCatalogRepository,
    ) -> None:
        draft = make_version()
        second_draft = replace(
            draft,
            id=PUBLISHED_VERSION_ID,
            version=2,
        )
        published = second_draft.submit_for_review(NOW).publish(NOW)

        await empty_catalog.add_tool(TENANT_A_ID, make_tool())
        await empty_catalog.add_version(TENANT_A_ID, draft)
        await empty_catalog.add_version(TENANT_A_ID, published)

        assert await empty_catalog.get_version_by_id(TENANT_A_ID, draft.id) == draft
        assert await empty_catalog.get_version_for_update(TENANT_A_ID, draft.id) == draft
        assert await empty_catalog.get_published_version(TENANT_A_ID, draft.tool_id) == published
        assert await empty_catalog.next_version_number(TENANT_A_ID, draft.tool_id) == 3
        assert await empty_catalog.get_version_by_id(TENANT_B_ID, draft.id) is None

        reviewed = draft.submit_for_review(NOW)
        await empty_catalog.save_version(TENANT_A_ID, reviewed)
        assert await empty_catalog.get_version_by_id(TENANT_A_ID, draft.id) == reviewed

    @pytest.mark.asyncio
    async def test_returns_tenant_scoped_published_projection(
        self,
        published_catalog: ToolCatalogRepository,
    ) -> None:
        tools = await published_catalog.list_published_by_tenant(TENANT_A_ID)

        assert tools == (make_published_tool(),)
        assert (
            await published_catalog.get_published_by_name(
                TENANT_A_ID,
                "directory.get_employee",
            )
            == tools[0]
        )
        assert await published_catalog.list_published_by_tenant(TENANT_B_ID) == ()

    @pytest.mark.asyncio
    async def test_rejects_entity_from_another_tenant(
        self,
        empty_catalog: ToolCatalogRepository,
    ) -> None:
        with pytest.raises(ValueError, match="tenant"):
            await empty_catalog.add_tool(TENANT_B_ID, make_tool(TENANT_A_ID))


class ToolBindingRepositoryContract:
    """所有 ToolBindingRepository Adapter 必须通过的可观察行为。"""

    @pytest.mark.asyncio
    async def test_stores_updates_and_tenant_scopes_binding(
        self,
        empty_bindings: ToolBindingRepository,
    ) -> None:
        binding = make_binding()

        await empty_bindings.add(TENANT_A_ID, binding)

        assert await empty_bindings.get_by_id(TENANT_A_ID, binding.id) == binding
        assert (
            await empty_bindings.get_by_tool_version(TENANT_A_ID, binding.tool_version_id)
            == binding
        )
        assert await empty_bindings.get_for_update(TENANT_A_ID, binding.id) == binding
        assert (
            await empty_bindings.get_by_tool_version_for_update(
                TENANT_A_ID,
                binding.tool_version_id,
            )
            == binding
        )
        assert await empty_bindings.get_by_id(TENANT_B_ID, binding.id) is None

        changed = replace(binding, binding_digest="3" * 64)
        await empty_bindings.save(TENANT_A_ID, changed)
        assert await empty_bindings.get_by_id(TENANT_A_ID, binding.id) == changed

    @pytest.mark.asyncio
    async def test_rejects_binding_from_another_tenant(
        self,
        empty_bindings: ToolBindingRepository,
    ) -> None:
        with pytest.raises(ValueError, match="tenant"):
            await empty_bindings.add(TENANT_B_ID, make_binding(TENANT_A_ID))


class CatalogUnitOfWorkContract:
    """所有 CatalogUnitOfWork Adapter 必须通过的事务行为。"""

    @pytest.mark.asyncio
    async def test_commit_persists_catalog_and_binding_together(
        self,
        unit_of_work_bundle: tuple[
            CatalogUnitOfWork,
            ToolCatalogRepository,
            ToolBindingRepository,
        ],
    ) -> None:
        unit_of_work, committed_catalog, committed_bindings = unit_of_work_bundle
        tool = make_tool()
        version = make_version()
        binding = make_binding()

        async with unit_of_work:
            await unit_of_work.catalog.add_tool(TENANT_A_ID, tool)
            await unit_of_work.catalog.add_version(TENANT_A_ID, version)
            await unit_of_work.bindings.add(TENANT_A_ID, binding)
            await unit_of_work.commit()

        assert await committed_catalog.get_tool_by_id(TENANT_A_ID, tool.id) == tool
        assert await committed_catalog.get_version_by_id(TENANT_A_ID, version.id) == version
        assert await committed_bindings.get_by_id(TENANT_A_ID, binding.id) == binding

    @pytest.mark.asyncio
    async def test_exit_without_commit_rolls_back_all_repositories(
        self,
        unit_of_work_bundle: tuple[
            CatalogUnitOfWork,
            ToolCatalogRepository,
            ToolBindingRepository,
        ],
    ) -> None:
        unit_of_work, committed_catalog, committed_bindings = unit_of_work_bundle

        async with unit_of_work:
            await unit_of_work.catalog.add_tool(TENANT_A_ID, make_tool())
            await unit_of_work.catalog.add_version(TENANT_A_ID, make_version())
            await unit_of_work.bindings.add(TENANT_A_ID, make_binding())

        assert await committed_catalog.get_tool_by_id(TENANT_A_ID, TOOL_ID) is None
        assert await committed_bindings.get_by_id(TENANT_A_ID, BINDING_ID) is None

    @pytest.mark.asyncio
    async def test_explicit_rollback_discards_all_pending_changes(
        self,
        unit_of_work_bundle: tuple[
            CatalogUnitOfWork,
            ToolCatalogRepository,
            ToolBindingRepository,
        ],
    ) -> None:
        unit_of_work, committed_catalog, committed_bindings = unit_of_work_bundle

        async with unit_of_work:
            await unit_of_work.catalog.add_tool(TENANT_A_ID, make_tool())
            await unit_of_work.catalog.add_version(TENANT_A_ID, make_version())
            await unit_of_work.bindings.add(TENANT_A_ID, make_binding())
            await unit_of_work.rollback()
            await unit_of_work.commit()

        assert await committed_catalog.get_tool_by_id(TENANT_A_ID, TOOL_ID) is None
        assert await committed_bindings.get_by_id(TENANT_A_ID, BINDING_ID) is None
