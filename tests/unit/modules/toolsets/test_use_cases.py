"""Toolset Admin Use Case 的 Aggregate、Revision 与 Catalog 校验。"""

from datetime import UTC, datetime

import pytest

from nexusmcp.modules.toolsets.adapters.in_memory import (
    InMemoryToolsetCatalogReader,
    InMemoryToolsetRepository,
)
from nexusmcp.modules.toolsets.adapters.in_memory_uow import InMemoryToolsetUnitOfWorkFactory
from nexusmcp.modules.toolsets.domain import (
    Toolset,
    ToolsetDiscoveryMode,
    ToolsetHealth,
    ToolsetMemberAvailability,
    ToolsetStatus,
)
from nexusmcp.modules.toolsets.errors import (
    SystemToolsetMutationError,
    ToolsetRevisionConflict,
)
from nexusmcp.modules.toolsets.ports import ToolsetCatalogSnapshot
from nexusmcp.modules.toolsets.use_cases import (
    ActivateToolset,
    ChangeToolsetStatusCommand,
    CreateToolset,
    CreateToolsetCommand,
    DisableToolset,
    EnsureAllPublishedToolset,
    GetToolset,
    ListToolsets,
    ListToolsetsQuery,
    ReplaceToolsetGrants,
    ReplaceToolsetGrantsCommand,
    ReplaceToolsetMembers,
    ReplaceToolsetMembersCommand,
    UpdateToolset,
    UpdateToolsetCommand,
    _map_mutation_error,
)
from nexusmcp.shared.errors import (
    InvalidToolsetMembersError,
    SystemToolsetImmutableError,
    ToolsetConflictError,
    ToolsetMemberUnavailableError,
    ToolsetRevisionConflictError,
)
from nexusmcp.shared.request_context import ActorContext

NOW = datetime(2026, 9, 7, tzinfo=UTC)


class FixedClock:
    def now(self) -> datetime:
        return NOW


class FixedIdentifierGenerator:
    def __init__(self, value: str = "toolset-1") -> None:
        self._value = value

    def new_id(self) -> str:
        return self._value


def context() -> ActorContext:
    return ActorContext(
        request_id="request-toolset-admin",
        trace_id="a" * 32,
        tenant_id="tenant-a",
        principal_id="admin-a",
        authn_method="test",
    )


def catalog() -> InMemoryToolsetCatalogReader:
    return InMemoryToolsetCatalogReader(
        (
            ToolsetCatalogSnapshot(
                tool_id="tool-a",
                tenant_id="tenant-a",
                availability=ToolsetMemberAvailability.AVAILABLE,
                published_tool_version_id="tool-a-v1",
                canonical_name="operations.get_incident",
                description="Get one incident",
                serialized_schema_size=128,
            ),
            ToolsetCatalogSnapshot(
                tool_id="tool-disabled",
                tenant_id="tenant-a",
                availability=ToolsetMemberAvailability.TOOL_DISABLED,
                published_tool_version_id=None,
                canonical_name="operations.disabled",
            ),
        )
    )


def factory() -> InMemoryToolsetUnitOfWorkFactory:
    return InMemoryToolsetUnitOfWorkFactory(
        toolsets=InMemoryToolsetRepository(),
        catalog=catalog(),
    )


@pytest.mark.asyncio
async def test_admin_use_cases_manage_explicit_toolset_lifecycle() -> None:
    uow_factory = factory()
    created = await CreateToolset(
        uow_factory,
        FixedIdentifierGenerator(),
        FixedClock(),
    ).execute(
        CreateToolsetCommand(
            context=context(),
            slug="operations",
            name="Operations",
            description="Operations tools",
        )
    )
    assert created.status is ToolsetStatus.DRAFT
    assert created.endpoint_path == "/mcp/toolsets/operations"
    assert created.health is ToolsetHealth.UNAVAILABLE

    with_member = await ReplaceToolsetMembers(uow_factory, FixedClock()).execute(
        ReplaceToolsetMembersCommand(
            context=context(),
            toolset_id=created.id,
            expected_revision=created.revision,
            tool_ids=("tool-a", "tool-a"),
        )
    )
    assert with_member.tool_count == 1
    assert with_member.available_tool_count == 1
    assert with_member.serialized_schema_size == 128
    assert with_member.health is ToolsetHealth.HEALTHY

    granted = await ReplaceToolsetGrants(uow_factory, FixedClock()).execute(
        ReplaceToolsetGrantsCommand(
            context=context(),
            toolset_id=created.id,
            expected_revision=with_member.revision,
            principal_ids=("sales-agent", "operations-agent"),
        )
    )
    assert granted.principal_ids == ("operations-agent", "sales-agent")

    active = await ActivateToolset(uow_factory, FixedClock()).execute(
        ChangeToolsetStatusCommand(
            context=context(),
            toolset_id=created.id,
            expected_revision=granted.revision,
        )
    )
    updated = await UpdateToolset(uow_factory, FixedClock()).execute(
        UpdateToolsetCommand(
            context=context(),
            toolset_id=created.id,
            expected_revision=active.revision,
            name="Platform Operations",
            description="Curated operations tools",
            discovery_mode=ToolsetDiscoveryMode.SEARCH_FIRST,
        )
    )
    disabled = await DisableToolset(uow_factory, FixedClock()).execute(
        ChangeToolsetStatusCommand(
            context=context(),
            toolset_id=created.id,
            expected_revision=updated.revision,
        )
    )

    assert disabled.status is ToolsetStatus.DISABLED
    assert disabled.discovery_mode is ToolsetDiscoveryMode.SEARCH_FIRST
    assert await GetToolset(uow_factory).execute(context(), created.id) == disabled
    page = await ListToolsets(uow_factory).execute(
        ListToolsetsQuery(context=context(), text="platform", status=ToolsetStatus.DISABLED)
    )
    assert page.items == (disabled,)
    assert page.total == 1


@pytest.mark.asyncio
async def test_create_rejects_duplicate_slug_and_update_rejects_stale_revision() -> None:
    uow_factory = factory()
    create = CreateToolset(uow_factory, FixedIdentifierGenerator(), FixedClock())
    command = CreateToolsetCommand(context=context(), slug="operations", name="Operations")
    created = await create.execute(command)

    with pytest.raises(ToolsetConflictError):
        await create.execute(command)
    with pytest.raises(ToolsetRevisionConflictError):
        await UpdateToolset(uow_factory, FixedClock()).execute(
            UpdateToolsetCommand(
                context=context(),
                toolset_id=created.id,
                expected_revision=created.revision + 1,
                name=created.name,
                description=created.description,
                discovery_mode=created.discovery_mode,
            )
        )


@pytest.mark.asyncio
async def test_member_validation_distinguishes_missing_and_unavailable_tools() -> None:
    uow_factory = factory()
    created = await CreateToolset(uow_factory, FixedIdentifierGenerator(), FixedClock()).execute(
        CreateToolsetCommand(context=context(), slug="operations", name="Operations")
    )

    with pytest.raises(InvalidToolsetMembersError):
        await ReplaceToolsetMembers(uow_factory, FixedClock()).execute(
            ReplaceToolsetMembersCommand(
                context=context(),
                toolset_id=created.id,
                expected_revision=created.revision,
                tool_ids=("missing",),
            )
        )

    draft = await ReplaceToolsetMembers(uow_factory, FixedClock()).execute(
        ReplaceToolsetMembersCommand(
            context=context(),
            toolset_id=created.id,
            expected_revision=created.revision,
            tool_ids=("tool-disabled",),
        )
    )
    assert draft.health is ToolsetHealth.UNAVAILABLE
    with pytest.raises(ToolsetMemberUnavailableError):
        await ActivateToolset(uow_factory, FixedClock()).execute(
            ChangeToolsetStatusCommand(
                context=context(),
                toolset_id=draft.id,
                expected_revision=draft.revision,
            )
        )


@pytest.mark.asyncio
async def test_system_toolset_cannot_be_disabled() -> None:
    repository = InMemoryToolsetRepository()
    system = Toolset.create_all_published(
        toolset_id="system-toolset",
        tenant_id="tenant-a",
        created_by="system",
        created_at=NOW,
    )
    await repository.add("tenant-a", system)
    uow_factory = InMemoryToolsetUnitOfWorkFactory(toolsets=repository, catalog=catalog())

    with pytest.raises(SystemToolsetImmutableError):
        await DisableToolset(uow_factory, FixedClock()).execute(
            ChangeToolsetStatusCommand(
                context=context(),
                toolset_id=system.id,
                expected_revision=system.revision,
            )
        )


@pytest.mark.asyncio
async def test_system_toolset_bootstrap_is_idempotent_and_only_appends_grants() -> None:
    repository = InMemoryToolsetRepository()
    uow_factory = InMemoryToolsetUnitOfWorkFactory(toolsets=repository, catalog=catalog())
    ensure = EnsureAllPublishedToolset(
        uow_factory,
        FixedIdentifierGenerator("system-toolset"),
        FixedClock(),
    )

    first = await ensure.execute("tenant-a", principal_ids=("agent-a",))
    second = await ensure.execute("tenant-a", principal_ids=("agent-b",))
    third = await ensure.execute("tenant-a", principal_ids=("agent-b",))

    assert first.principal_ids == ("agent-a",)
    assert second.principal_ids == ("agent-a", "agent-b")
    assert third == second
    assert await repository.list_by_tenant("tenant-a") == (second,)


def test_typed_domain_error_mapping_does_not_depend_on_exception_message() -> None:
    assert isinstance(
        _map_mutation_error(ToolsetRevisionConflict("aggregate changed")),
        ToolsetRevisionConflictError,
    )
    assert isinstance(
        _map_mutation_error(SystemToolsetMutationError("operation forbidden")),
        SystemToolsetImmutableError,
    )
