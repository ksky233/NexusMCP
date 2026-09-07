"""Toolset Admin Command、Query 与管理端 Profile。"""

from dataclasses import dataclass
from datetime import datetime

from nexusmcp.modules.control_plane.read_models import Page
from nexusmcp.modules.toolsets.domain import (
    Toolset,
    ToolsetDiscoveryMode,
    ToolsetHealth,
    ToolsetKind,
    ToolsetMemberAvailability,
    ToolsetStatus,
)
from nexusmcp.modules.toolsets.ports import (
    ToolsetCatalogSnapshot,
    ToolsetUnitOfWork,
    ToolsetUnitOfWorkFactory,
)
from nexusmcp.shared.clock import Clock
from nexusmcp.shared.errors import (
    InvalidArgumentsError,
    InvalidToolsetMembersError,
    SystemToolsetImmutableError,
    ToolsetConflictError,
    ToolsetMemberUnavailableError,
    ToolsetNotFoundError,
    ToolsetRevisionConflictError,
)
from nexusmcp.shared.identifiers import IdentifierGenerator
from nexusmcp.shared.request_context import ActorContext


@dataclass(frozen=True, slots=True, kw_only=True)
class CreateToolsetCommand:
    context: ActorContext
    slug: str
    name: str
    description: str | None = None
    discovery_mode: ToolsetDiscoveryMode = ToolsetDiscoveryMode.DIRECT


@dataclass(frozen=True, slots=True, kw_only=True)
class UpdateToolsetCommand:
    context: ActorContext
    toolset_id: str
    expected_revision: int
    name: str
    description: str | None
    discovery_mode: ToolsetDiscoveryMode


@dataclass(frozen=True, slots=True, kw_only=True)
class ReplaceToolsetMembersCommand:
    context: ActorContext
    toolset_id: str
    expected_revision: int
    tool_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class ReplaceToolsetGrantsCommand:
    context: ActorContext
    toolset_id: str
    expected_revision: int
    principal_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class ChangeToolsetStatusCommand:
    context: ActorContext
    toolset_id: str
    expected_revision: int


@dataclass(frozen=True, slots=True, kw_only=True)
class ListToolsetsQuery:
    context: ActorContext
    offset: int = 0
    limit: int = 50
    text: str | None = None
    status: ToolsetStatus | None = None
    kind: ToolsetKind | None = None
    discovery_mode: ToolsetDiscoveryMode | None = None


@dataclass(frozen=True, slots=True)
class ToolsetMemberProfile:
    tool_id: str
    canonical_name: str | None
    description: str | None
    availability: ToolsetMemberAvailability
    published_tool_version_id: str | None
    serialized_schema_size: int


@dataclass(frozen=True, slots=True)
class ToolsetProfile:
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
    principal_ids: tuple[str, ...]
    members: tuple[ToolsetMemberProfile, ...]
    created_by: str
    created_at: datetime
    updated_at: datetime


class CreateToolset:
    def __init__(
        self,
        unit_of_work_factory: ToolsetUnitOfWorkFactory,
        identifier_generator: IdentifierGenerator,
        clock: Clock,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._identifier_generator = identifier_generator
        self._clock = clock

    async def execute(self, command: CreateToolsetCommand) -> ToolsetProfile:
        now = self._clock.now()
        try:
            toolset = Toolset.create_explicit(
                toolset_id=self._identifier_generator.new_id(),
                tenant_id=command.context.tenant_id,
                slug=command.slug,
                name=command.name,
                description=command.description,
                created_by=command.context.principal_id,
                created_at=now,
                discovery_mode=command.discovery_mode,
            )
        except ValueError as error:
            raise InvalidArgumentsError(str(error)) from error
        async with self._unit_of_work_factory() as unit_of_work:
            if await unit_of_work.toolsets.get_by_slug(toolset.tenant_id, toolset.slug):
                raise ToolsetConflictError("toolset slug already exists in tenant")
            try:
                await unit_of_work.toolsets.add(toolset.tenant_id, toolset)
                await unit_of_work.commit()
            except ValueError as error:
                raise ToolsetConflictError(str(error)) from error
        return await GetToolset(self._unit_of_work_factory).execute(
            command.context,
            toolset.id,
        )


class UpdateToolset:
    def __init__(self, unit_of_work_factory: ToolsetUnitOfWorkFactory, clock: Clock) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._clock = clock

    async def execute(self, command: UpdateToolsetCommand) -> ToolsetProfile:
        async with self._unit_of_work_factory() as unit_of_work:
            toolset = await _get_locked(unit_of_work, command.context, command.toolset_id)
            try:
                updated = toolset.update_profile(
                    expected_revision=command.expected_revision,
                    name=command.name,
                    description=command.description,
                    discovery_mode=command.discovery_mode,
                    updated_at=self._clock.now(),
                )
                await unit_of_work.toolsets.save(command.context.tenant_id, updated)
            except ValueError as error:
                raise _map_mutation_error(error) from error
            profile = await _profile(unit_of_work, updated)
            await unit_of_work.commit()
            return profile


class ReplaceToolsetMembers:
    def __init__(self, unit_of_work_factory: ToolsetUnitOfWorkFactory, clock: Clock) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._clock = clock

    async def execute(self, command: ReplaceToolsetMembersCommand) -> ToolsetProfile:
        async with self._unit_of_work_factory() as unit_of_work:
            toolset = await _get_locked(unit_of_work, command.context, command.toolset_id)
            _require_expected_revision(toolset, command.expected_revision)
            requested = tuple(sorted(set(command.tool_ids)))
            snapshots = await unit_of_work.catalog.list_member_snapshots(
                command.context.tenant_id,
                requested,
            )
            if {snapshot.tool_id for snapshot in snapshots} != set(requested):
                raise InvalidToolsetMembersError("one or more tools did not exist in tenant")
            if toolset.status is ToolsetStatus.ACTIVE:
                _require_available(snapshots)
            try:
                updated = toolset.replace_members(
                    expected_revision=command.expected_revision,
                    tool_ids=requested,
                    actor_id=command.context.principal_id,
                    occurred_at=self._clock.now(),
                )
                await unit_of_work.toolsets.save(command.context.tenant_id, updated)
            except ValueError as error:
                raise _map_mutation_error(error) from error
            profile = await _profile(unit_of_work, updated)
            await unit_of_work.commit()
            return profile


class ReplaceToolsetGrants:
    def __init__(self, unit_of_work_factory: ToolsetUnitOfWorkFactory, clock: Clock) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._clock = clock

    async def execute(self, command: ReplaceToolsetGrantsCommand) -> ToolsetProfile:
        async with self._unit_of_work_factory() as unit_of_work:
            toolset = await _get_locked(unit_of_work, command.context, command.toolset_id)
            try:
                updated = toolset.replace_grants(
                    expected_revision=command.expected_revision,
                    principal_ids=command.principal_ids,
                    actor_id=command.context.principal_id,
                    occurred_at=self._clock.now(),
                )
                await unit_of_work.toolsets.save(command.context.tenant_id, updated)
            except ValueError as error:
                raise _map_mutation_error(error) from error
            profile = await _profile(unit_of_work, updated)
            await unit_of_work.commit()
            return profile


class ActivateToolset:
    def __init__(self, unit_of_work_factory: ToolsetUnitOfWorkFactory, clock: Clock) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._clock = clock

    async def execute(self, command: ChangeToolsetStatusCommand) -> ToolsetProfile:
        async with self._unit_of_work_factory() as unit_of_work:
            toolset = await _get_locked(unit_of_work, command.context, command.toolset_id)
            _require_expected_revision(toolset, command.expected_revision)
            snapshots = await unit_of_work.catalog.list_member_snapshots(
                command.context.tenant_id,
                toolset.tool_ids,
            )
            _require_available(snapshots, expected_count=len(toolset.tool_ids))
            try:
                updated = toolset.activate(
                    expected_revision=command.expected_revision,
                    activated_at=self._clock.now(),
                )
                await unit_of_work.toolsets.save(command.context.tenant_id, updated)
            except ValueError as error:
                raise _map_mutation_error(error) from error
            profile = await _profile(unit_of_work, updated)
            await unit_of_work.commit()
            return profile


class DisableToolset:
    def __init__(self, unit_of_work_factory: ToolsetUnitOfWorkFactory, clock: Clock) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._clock = clock

    async def execute(self, command: ChangeToolsetStatusCommand) -> ToolsetProfile:
        async with self._unit_of_work_factory() as unit_of_work:
            toolset = await _get_locked(unit_of_work, command.context, command.toolset_id)
            try:
                updated = toolset.disable(
                    expected_revision=command.expected_revision,
                    disabled_at=self._clock.now(),
                )
                await unit_of_work.toolsets.save(command.context.tenant_id, updated)
            except ValueError as error:
                raise _map_mutation_error(error) from error
            profile = await _profile(unit_of_work, updated)
            await unit_of_work.commit()
            return profile


class GetToolset:
    def __init__(self, unit_of_work_factory: ToolsetUnitOfWorkFactory) -> None:
        self._unit_of_work_factory = unit_of_work_factory

    async def execute(self, context: ActorContext, toolset_id: str) -> ToolsetProfile:
        async with self._unit_of_work_factory() as unit_of_work:
            toolset = await unit_of_work.toolsets.get_by_id(context.tenant_id, toolset_id)
            if toolset is None:
                raise ToolsetNotFoundError("toolset did not exist in tenant")
            return await _profile(unit_of_work, toolset)


class ListToolsets:
    def __init__(self, unit_of_work_factory: ToolsetUnitOfWorkFactory) -> None:
        self._unit_of_work_factory = unit_of_work_factory

    async def execute(self, query: ListToolsetsQuery) -> Page[ToolsetProfile]:
        async with self._unit_of_work_factory() as unit_of_work:
            candidates = await unit_of_work.toolsets.list_by_tenant(query.context.tenant_id)
            text = query.text.casefold().strip() if query.text else None
            selected = tuple(
                toolset
                for toolset in candidates
                if (text is None or text in f"{toolset.name} {toolset.slug}".casefold())
                and (query.status is None or toolset.status is query.status)
                and (query.kind is None or toolset.kind is query.kind)
                and (query.discovery_mode is None or toolset.discovery_mode is query.discovery_mode)
            )
            window = selected[query.offset : query.offset + query.limit]
            profiles = tuple([await _profile(unit_of_work, toolset) for toolset in window])
            return Page(
                items=profiles,
                offset=query.offset,
                limit=query.limit,
                total=len(selected),
            )


async def _get_locked(
    unit_of_work: ToolsetUnitOfWork,
    context: ActorContext,
    toolset_id: str,
) -> Toolset:
    toolset = await unit_of_work.toolsets.get_for_update(context.tenant_id, toolset_id)
    if toolset is None:
        raise ToolsetNotFoundError("toolset did not exist in tenant")
    return toolset


async def _profile(
    unit_of_work: ToolsetUnitOfWork,
    toolset: Toolset,
) -> ToolsetProfile:
    snapshots = (
        await unit_of_work.catalog.list_published_snapshots(toolset.tenant_id)
        if toolset.kind is ToolsetKind.ALL_PUBLISHED
        else await unit_of_work.catalog.list_member_snapshots(toolset.tenant_id, toolset.tool_ids)
    )
    profiles = tuple(_member_profile(snapshot) for snapshot in snapshots)
    available_count = sum(
        profile.availability is ToolsetMemberAvailability.AVAILABLE for profile in profiles
    )
    expected_count = (
        len(profiles) if toolset.kind is ToolsetKind.ALL_PUBLISHED else len(toolset.members)
    )
    health = (
        ToolsetHealth.UNAVAILABLE
        if expected_count == 0 or available_count == 0
        else ToolsetHealth.HEALTHY
        if available_count == expected_count
        else ToolsetHealth.DEGRADED
    )
    return ToolsetProfile(
        id=toolset.id,
        tenant_id=toolset.tenant_id,
        slug=toolset.slug,
        name=toolset.name,
        description=toolset.description,
        kind=toolset.kind,
        discovery_mode=toolset.discovery_mode,
        status=toolset.status,
        revision=toolset.revision,
        membership_digest=toolset.membership_digest,
        endpoint_path=f"/mcp/toolsets/{toolset.slug}",
        health=health,
        tool_count=expected_count,
        available_tool_count=available_count,
        serialized_schema_size=sum(profile.serialized_schema_size for profile in profiles),
        principal_ids=toolset.principal_ids,
        members=profiles,
        created_by=toolset.created_by,
        created_at=toolset.created_at,
        updated_at=toolset.updated_at,
    )


def _member_profile(snapshot: ToolsetCatalogSnapshot) -> ToolsetMemberProfile:
    return ToolsetMemberProfile(
        tool_id=snapshot.tool_id,
        canonical_name=snapshot.canonical_name,
        description=snapshot.description,
        availability=snapshot.availability,
        published_tool_version_id=snapshot.published_tool_version_id,
        serialized_schema_size=snapshot.serialized_schema_size,
    )


def _require_available(
    snapshots: tuple[ToolsetCatalogSnapshot, ...],
    *,
    expected_count: int | None = None,
) -> None:
    if expected_count is not None and len(snapshots) != expected_count:
        raise InvalidToolsetMembersError("one or more tools did not exist in tenant")
    if any(
        snapshot.availability is not ToolsetMemberAvailability.AVAILABLE for snapshot in snapshots
    ):
        raise ToolsetMemberUnavailableError("one or more tools were not currently published")


def _require_expected_revision(toolset: Toolset, expected_revision: int) -> None:
    if toolset.revision != expected_revision:
        raise ToolsetRevisionConflictError("toolset revision conflict")


def _map_mutation_error(error: ValueError) -> Exception:
    message = str(error)
    if "revision" in message:
        return ToolsetRevisionConflictError(message)
    if "all_published" in message or "system" in message:
        return SystemToolsetImmutableError(message)
    return InvalidArgumentsError(message)
