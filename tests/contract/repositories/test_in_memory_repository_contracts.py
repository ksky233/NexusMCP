"""由 InMemory Adapter 首先执行、未来由 PostgreSQL Adapter 复用的 Port Contract。"""

from dataclasses import replace
from datetime import UTC, datetime

import pytest

from nexusmcp.modules.catalog.adapters.in_memory import InMemoryToolCatalogRepository
from nexusmcp.modules.catalog.adapters.in_memory_uow import InMemoryCatalogUnitOfWork
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
from nexusmcp.modules.connectors.adapters.in_memory import InMemoryToolBindingRepository
from nexusmcp.modules.connectors.domain import (
    ToolBinding,
    ToolBindingStatus,
    ToolBindingType,
)
from nexusmcp.modules.connectors.ports import ToolBindingRepository

NOW = datetime(2026, 8, 25, tzinfo=UTC)


def _tool(tenant_id: str = "tenant-a") -> Tool:
    return Tool(
        id=f"tool-{tenant_id}",
        tenant_id=tenant_id,
        namespace="directory",
        canonical_name="directory.get_employee",
        owner="people-platform",
    )


def _version(
    tenant_id: str = "tenant-a",
    status: ToolVersionStatus = ToolVersionStatus.DRAFT,
) -> ToolVersion:
    return ToolVersion(
        id=f"version-{tenant_id}",
        tenant_id=tenant_id,
        tool_id=f"tool-{tenant_id}",
        version=1,
        display_name="Get employee",
        description="Get one employee by id.",
        input_schema={"type": "object", "properties": {}},
        output_schema=None,
        schema_digest="schema-directory-get-employee-v1",
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


def _published_tool(tenant_id: str = "tenant-a") -> PublishedTool:
    return PublishedTool(
        tool_id=f"tool-{tenant_id}",
        tool_version_id=f"version-{tenant_id}",
        tenant_id=tenant_id,
        canonical_name="directory.get_employee",
        display_name="Get employee",
        description="Get one employee by id.",
        input_schema={"type": "object", "properties": {}},
        output_schema=None,
        version=1,
        visibility=ToolVisibility.PUBLIC,
        side_effect=ToolSideEffect.READ_ONLY,
        schema_digest="schema-directory-get-employee-v1",
    )


def _binding(tenant_id: str = "tenant-a") -> ToolBinding:
    return ToolBinding(
        id=f"binding-{tenant_id}",
        tenant_id=tenant_id,
        tool_version_id=f"version-{tenant_id}",
        upstream_service_id=f"upstream-{tenant_id}",
        imported_operation_id=None,
        binding_type=ToolBindingType.HTTP,
        binding_config={"method": "GET", "path_template": "/employees/{employee_id}"},
        binding_digest="binding-directory-get-employee-v1",
        status=ToolBindingStatus.DRAFT,
        created_at=NOW,
    )


class CatalogRepositoryContract:
    """所有 ToolCatalogRepository Adapter 必须通过的可观察行为。"""

    @pytest.fixture
    def empty_catalog(self) -> ToolCatalogRepository:
        raise NotImplementedError

    @pytest.fixture
    def published_catalog(self) -> ToolCatalogRepository:
        raise NotImplementedError

    @pytest.mark.asyncio
    async def test_stores_updates_and_tenant_scopes_tool_identity(
        self,
        empty_catalog: ToolCatalogRepository,
    ) -> None:
        tool = _tool()

        await empty_catalog.add_tool("tenant-a", tool)

        assert await empty_catalog.get_tool_by_id("tenant-a", tool.id) == tool
        assert await empty_catalog.get_tool_by_name("tenant-a", tool.canonical_name) == tool
        assert await empty_catalog.get_tool_for_update("tenant-a", tool.id) == tool
        assert await empty_catalog.get_tool_by_id("tenant-b", tool.id) is None

        disabled = replace(tool, status=ToolStatus.DISABLED)
        await empty_catalog.save_tool("tenant-a", disabled)
        assert await empty_catalog.get_tool_by_id("tenant-a", tool.id) == disabled

    @pytest.mark.asyncio
    async def test_stores_versions_and_finds_only_the_published_version(
        self,
        empty_catalog: ToolCatalogRepository,
    ) -> None:
        draft = _version()
        second_draft = replace(
            draft,
            id="version-published",
            version=2,
        )
        published = second_draft.submit_for_review(NOW).publish(NOW)

        await empty_catalog.add_tool("tenant-a", _tool())
        await empty_catalog.add_version("tenant-a", draft)
        await empty_catalog.add_version("tenant-a", published)

        assert await empty_catalog.get_version_by_id("tenant-a", draft.id) == draft
        assert await empty_catalog.get_version_for_update("tenant-a", draft.id) == draft
        assert await empty_catalog.get_published_version("tenant-a", draft.tool_id) == published
        assert await empty_catalog.get_version_by_id("tenant-b", draft.id) is None

        reviewed = draft.submit_for_review(NOW)
        await empty_catalog.save_version("tenant-a", reviewed)
        assert await empty_catalog.get_version_by_id("tenant-a", draft.id) == reviewed

    @pytest.mark.asyncio
    async def test_returns_tenant_scoped_published_projection(
        self,
        published_catalog: ToolCatalogRepository,
    ) -> None:
        tools = await published_catalog.list_published_by_tenant("tenant-a")

        assert tools == (_published_tool(),)
        assert (
            await published_catalog.get_published_by_name(
                "tenant-a",
                "directory.get_employee",
            )
            == tools[0]
        )
        assert await published_catalog.list_published_by_tenant("tenant-b") == ()

    @pytest.mark.asyncio
    async def test_rejects_entity_from_another_tenant(
        self,
        empty_catalog: ToolCatalogRepository,
    ) -> None:
        with pytest.raises(ValueError, match="tenant"):
            await empty_catalog.add_tool("tenant-b", _tool("tenant-a"))


class ToolBindingRepositoryContract:
    """所有 ToolBindingRepository Adapter 必须通过的可观察行为。"""

    @pytest.fixture
    def empty_bindings(self) -> ToolBindingRepository:
        raise NotImplementedError

    @pytest.mark.asyncio
    async def test_stores_updates_and_tenant_scopes_binding(
        self,
        empty_bindings: ToolBindingRepository,
    ) -> None:
        binding = _binding()

        await empty_bindings.add("tenant-a", binding)

        assert await empty_bindings.get_by_id("tenant-a", binding.id) == binding
        assert (
            await empty_bindings.get_by_tool_version("tenant-a", binding.tool_version_id) == binding
        )
        assert await empty_bindings.get_for_update("tenant-a", binding.id) == binding
        assert await empty_bindings.get_by_id("tenant-b", binding.id) is None

        changed = replace(binding, binding_digest="changed-binding-digest")
        await empty_bindings.save("tenant-a", changed)
        assert await empty_bindings.get_by_id("tenant-a", binding.id) == changed

    @pytest.mark.asyncio
    async def test_rejects_binding_from_another_tenant(
        self,
        empty_bindings: ToolBindingRepository,
    ) -> None:
        with pytest.raises(ValueError, match="tenant"):
            await empty_bindings.add("tenant-b", _binding("tenant-a"))


class CatalogUnitOfWorkContract:
    """所有 CatalogUnitOfWork Adapter 必须通过的事务行为。"""

    @pytest.fixture
    def unit_of_work_bundle(
        self,
    ) -> tuple[CatalogUnitOfWork, ToolCatalogRepository, ToolBindingRepository]:
        raise NotImplementedError

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
        tool = _tool()
        version = _version()
        binding = _binding()

        async with unit_of_work:
            await unit_of_work.catalog.add_tool("tenant-a", tool)
            await unit_of_work.catalog.add_version("tenant-a", version)
            await unit_of_work.bindings.add("tenant-a", binding)
            await unit_of_work.commit()

        assert await committed_catalog.get_tool_by_id("tenant-a", tool.id) == tool
        assert await committed_catalog.get_version_by_id("tenant-a", version.id) == version
        assert await committed_bindings.get_by_id("tenant-a", binding.id) == binding

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
            await unit_of_work.catalog.add_tool("tenant-a", _tool())
            await unit_of_work.bindings.add("tenant-a", _binding())

        assert await committed_catalog.get_tool_by_id("tenant-a", "tool-tenant-a") is None
        assert await committed_bindings.get_by_id("tenant-a", "binding-tenant-a") is None

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
            await unit_of_work.catalog.add_tool("tenant-a", _tool())
            await unit_of_work.bindings.add("tenant-a", _binding())
            await unit_of_work.rollback()
            await unit_of_work.commit()

        assert await committed_catalog.get_tool_by_id("tenant-a", "tool-tenant-a") is None
        assert await committed_bindings.get_by_id("tenant-a", "binding-tenant-a") is None


class TestInMemoryToolCatalogRepository(CatalogRepositoryContract):
    @pytest.fixture
    def empty_catalog(self) -> ToolCatalogRepository:
        return InMemoryToolCatalogRepository()

    @pytest.fixture
    def published_catalog(self) -> ToolCatalogRepository:
        return InMemoryToolCatalogRepository(published_tools=[_published_tool()])


class TestInMemoryToolBindingRepository(ToolBindingRepositoryContract):
    @pytest.fixture
    def empty_bindings(self) -> ToolBindingRepository:
        return InMemoryToolBindingRepository()


class TestInMemoryCatalogUnitOfWork(CatalogUnitOfWorkContract):
    @pytest.fixture
    def unit_of_work_bundle(
        self,
    ) -> tuple[CatalogUnitOfWork, ToolCatalogRepository, ToolBindingRepository]:
        catalog = InMemoryToolCatalogRepository()
        bindings = InMemoryToolBindingRepository()
        return InMemoryCatalogUnitOfWork(catalog, bindings), catalog, bindings
