"""Publish Tool 原子状态切换、校验和事件测试。"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime

import pytest

from nexusmcp.modules.catalog.adapters.in_memory import InMemoryToolCatalogRepository
from nexusmcp.modules.catalog.adapters.in_memory_uow import (
    InMemoryCatalogUnitOfWork,
    InMemoryCatalogUnitOfWorkFactory,
)
from nexusmcp.modules.catalog.digests import calculate_schema_digest
from nexusmcp.modules.catalog.domain import (
    Tool,
    ToolSideEffect,
    ToolStatus,
    ToolVersion,
    ToolVersionStatus,
    ToolVisibility,
)
from nexusmcp.modules.catalog.publish import PublishTool, PublishToolCommand
from nexusmcp.modules.connectors.adapters.in_memory import InMemoryToolBindingRepository
from nexusmcp.modules.connectors.digests import calculate_binding_digest
from nexusmcp.modules.connectors.domain import (
    ToolBinding,
    ToolBindingStatus,
    ToolBindingType,
)
from nexusmcp.modules.registry.adapters.in_memory import InMemoryUpstreamRepository
from nexusmcp.modules.registry.domain import (
    UpstreamService,
    UpstreamServiceType,
    UpstreamStatus,
)
from nexusmcp.shared.errors import (
    BindingDigestMismatchError,
    InvalidToolStateError,
    PublishConflictError,
    SchemaDigestMismatchError,
    TenantBoundaryViolationError,
    UpstreamNotActiveError,
)
from nexusmcp.shared.request_context import ProtocolEra, RequestContext

TENANT_ID = "tenant-a"
TOOL_ID = "tool-1"
TARGET_VERSION_ID = "version-2"
TARGET_BINDING_ID = "binding-2"
UPSTREAM_ID = "upstream-1"
NOW = datetime(2026, 8, 25, 10, 30, tzinfo=UTC)


@dataclass(frozen=True, slots=True)
class FixedClock:
    value: datetime

    def now(self) -> datetime:
        return self.value


def _context() -> RequestContext:
    return RequestContext(
        request_id="request-publish",
        trace_id="1" * 32,
        protocol_version="2026-07-28",
        protocol_era=ProtocolEra.MODERN,
        tenant_id=TENANT_ID,
        principal_id="publisher-1",
        authn_method="test",
    )


def _tool() -> Tool:
    return Tool(
        id=TOOL_ID,
        tenant_id=TENANT_ID,
        namespace="directory",
        canonical_name="directory.get_employee",
        owner="people-platform",
        status=ToolStatus.DISABLED,
    )


def _version(
    version_id: str = TARGET_VERSION_ID,
    version_number: int = 2,
    status: ToolVersionStatus = ToolVersionStatus.REVIEW,
) -> ToolVersion:
    input_schema = {
        "type": "object",
        "properties": {"employee_id": {"type": "string"}},
        "required": ["employee_id"],
    }
    return ToolVersion(
        id=version_id,
        tenant_id=TENANT_ID,
        tool_id=TOOL_ID,
        version=version_number,
        display_name="Get employee",
        description="Get one employee by id.",
        input_schema=input_schema,
        output_schema=None,
        schema_digest=calculate_schema_digest(input_schema, None),
        tags=("directory",),
        side_effect=ToolSideEffect.READ_ONLY,
        visibility=ToolVisibility.PUBLIC,
        status=status,
        created_by="reviewer-1",
        created_at=NOW,
        reviewed_at=NOW if status is not ToolVersionStatus.DRAFT else None,
        published_at=NOW if status is ToolVersionStatus.PUBLISHED else None,
    )


def _binding(
    binding_id: str = TARGET_BINDING_ID,
    version_id: str = TARGET_VERSION_ID,
    status: ToolBindingStatus = ToolBindingStatus.DRAFT,
) -> ToolBinding:
    binding = ToolBinding(
        id=binding_id,
        tenant_id=TENANT_ID,
        tool_version_id=version_id,
        upstream_service_id=UPSTREAM_ID,
        imported_operation_id=None,
        binding_type=ToolBindingType.HTTP,
        binding_config={"method": "GET", "path_template": "/employees/{employee_id}"},
        binding_digest="pending",
        status=status,
        created_at=NOW,
        published_at=NOW if status is ToolBindingStatus.PUBLISHED else None,
    )
    return replace(binding, binding_digest=calculate_binding_digest(binding))


def _upstream(
    status: UpstreamStatus = UpstreamStatus.ACTIVE,
    tenant_id: str = TENANT_ID,
) -> UpstreamService:
    return UpstreamService(
        id=UPSTREAM_ID,
        tenant_id=tenant_id,
        namespace="directory",
        name="employee-directory",
        description="Employee directory test upstream",
        owner="people-platform",
        service_type=UpstreamServiceType.HTTP,
        transport_type="http",
        endpoint="http://127.0.0.1:9001",
        protocol_min=None,
        protocol_max=None,
        auth_scheme="none",
        config={},
        status=status,
    )


def _command(version: ToolVersion, binding: ToolBinding) -> PublishToolCommand:
    return PublishToolCommand(
        context=_context(),
        tool_id=TOOL_ID,
        tool_version_id=version.id,
        expected_schema_digest=version.schema_digest,
        expected_binding_digest=binding.binding_digest,
    )


def _build_use_case(
    *,
    versions: list[ToolVersion],
    bindings: list[ToolBinding],
    upstream: UpstreamService | None = None,
) -> tuple[
    PublishTool,
    InMemoryToolCatalogRepository,
    InMemoryToolBindingRepository,
    InMemoryUpstreamRepository,
]:
    catalog = InMemoryToolCatalogRepository(tools=[_tool()], versions=versions)
    binding_repository = InMemoryToolBindingRepository(bindings)
    upstream_repository = InMemoryUpstreamRepository([upstream or _upstream()])
    factory = InMemoryCatalogUnitOfWorkFactory(
        catalog,
        binding_repository,
        upstream_repository,
    )
    return (
        PublishTool(factory, FixedClock(NOW)),
        catalog,
        binding_repository,
        upstream_repository,
    )


@pytest.mark.asyncio
async def test_publish_first_version_activates_tool_binding_and_event() -> None:
    version = _version(version_number=1)
    binding = _binding()
    use_case, catalog, bindings, _upstreams = _build_use_case(
        versions=[version],
        bindings=[binding],
    )

    result = await use_case.execute(_command(version, binding))

    assert (await catalog.get_tool_by_id(TENANT_ID, TOOL_ID)).status is ToolStatus.ACTIVE  # type: ignore[union-attr]
    assert (
        await catalog.get_version_by_id(TENANT_ID, version.id)
    ).status is ToolVersionStatus.PUBLISHED  # type: ignore[union-attr]
    assert (await bindings.get_by_id(TENANT_ID, binding.id)).status is ToolBindingStatus.PUBLISHED  # type: ignore[union-attr]
    assert result.retired_tool_version_id is None
    assert result.event.tool_version_id == version.id
    assert result.event.actor_id == "publisher-1"
    assert result.event.occurred_at == NOW


@pytest.mark.asyncio
async def test_publish_new_version_retires_previous_version_and_binding() -> None:
    previous = _version("version-1", 1, ToolVersionStatus.PUBLISHED)
    previous_binding = _binding("binding-1", "version-1", ToolBindingStatus.PUBLISHED)
    target = _version()
    target_binding = _binding()
    use_case, catalog, bindings, _upstreams = _build_use_case(
        versions=[previous, target],
        bindings=[previous_binding, target_binding],
    )

    result = await use_case.execute(_command(target, target_binding))

    assert result.retired_tool_version_id == previous.id
    assert (
        await catalog.get_version_by_id(TENANT_ID, previous.id)
    ).status is ToolVersionStatus.RETIRED  # type: ignore[union-attr]
    assert (
        await bindings.get_by_id(TENANT_ID, previous_binding.id)
    ).status is ToolBindingStatus.DISABLED  # type: ignore[union-attr]
    assert (
        await catalog.get_version_by_id(TENANT_ID, target.id)
    ).status is ToolVersionStatus.PUBLISHED  # type: ignore[union-attr]


@pytest.mark.asyncio
async def test_publish_rejects_invalid_state_without_persisting_changes() -> None:
    draft = _version(status=ToolVersionStatus.DRAFT)
    binding = _binding()
    use_case, catalog, bindings, _upstreams = _build_use_case(
        versions=[draft],
        bindings=[binding],
    )

    with pytest.raises(InvalidToolStateError):
        await use_case.execute(_command(draft, binding))

    assert (await catalog.get_tool_by_id(TENANT_ID, TOOL_ID)).status is ToolStatus.DISABLED  # type: ignore[union-attr]
    assert (await catalog.get_version_by_id(TENANT_ID, draft.id)).status is ToolVersionStatus.DRAFT  # type: ignore[union-attr]
    assert (await bindings.get_by_id(TENANT_ID, binding.id)).status is ToolBindingStatus.DRAFT  # type: ignore[union-attr]


@pytest.mark.asyncio
async def test_publish_rejects_schema_and_binding_digest_changes() -> None:
    version = _version()
    binding = _binding()
    use_case, _catalog, _bindings, _upstreams = _build_use_case(
        versions=[version],
        bindings=[binding],
    )

    with pytest.raises(SchemaDigestMismatchError):
        await use_case.execute(replace(_command(version, binding), expected_schema_digest="stale"))
    with pytest.raises(BindingDigestMismatchError):
        await use_case.execute(replace(_command(version, binding), expected_binding_digest="stale"))


@pytest.mark.asyncio
async def test_publish_recalculates_stored_schema_and_binding_digests() -> None:
    version = _version()
    binding = _binding()
    tampered_version = replace(
        version,
        input_schema={"type": "object", "properties": {"unexpected": {"type": "string"}}},
    )
    tampered_binding = replace(
        binding,
        binding_config={"method": "DELETE", "path_template": "/employees/{employee_id}"},
    )
    schema_use_case, *_ = _build_use_case(
        versions=[tampered_version],
        bindings=[binding],
    )
    binding_use_case, *_ = _build_use_case(
        versions=[version],
        bindings=[tampered_binding],
    )

    with pytest.raises(SchemaDigestMismatchError):
        await schema_use_case.execute(_command(tampered_version, binding))
    with pytest.raises(BindingDigestMismatchError):
        await binding_use_case.execute(_command(version, tampered_binding))


@pytest.mark.asyncio
async def test_publish_rejects_version_that_is_not_newer_than_current() -> None:
    current = _version("version-current", 2, ToolVersionStatus.PUBLISHED)
    current_binding = _binding(
        "binding-current",
        "version-current",
        ToolBindingStatus.PUBLISHED,
    )
    target = _version(version_number=1)
    target_binding = _binding()
    use_case, *_ = _build_use_case(
        versions=[current, target],
        bindings=[current_binding, target_binding],
    )

    with pytest.raises(PublishConflictError):
        await use_case.execute(_command(target, target_binding))


@pytest.mark.asyncio
async def test_publish_rejects_inactive_or_cross_tenant_upstream() -> None:
    version = _version()
    binding = _binding()
    inactive_use_case, *_ = _build_use_case(
        versions=[version],
        bindings=[binding],
        upstream=_upstream(UpstreamStatus.DISABLED),
    )
    cross_tenant_use_case, *_ = _build_use_case(
        versions=[version],
        bindings=[binding],
        upstream=_upstream(tenant_id="tenant-b"),
    )

    with pytest.raises(UpstreamNotActiveError):
        await inactive_use_case.execute(_command(version, binding))
    with pytest.raises(TenantBoundaryViolationError):
        await cross_tenant_use_case.execute(_command(version, binding))


class FailingCommitUnitOfWork(InMemoryCatalogUnitOfWork):
    async def __aenter__(self) -> FailingCommitUnitOfWork:
        await super().__aenter__()
        return self

    async def commit(self) -> None:
        raise RuntimeError("simulated commit failure")


class FailingCommitFactory:
    def __init__(
        self,
        catalog: InMemoryToolCatalogRepository,
        bindings: InMemoryToolBindingRepository,
        upstreams: InMemoryUpstreamRepository,
    ) -> None:
        self._catalog = catalog
        self._bindings = bindings
        self._upstreams = upstreams

    def __call__(self) -> FailingCommitUnitOfWork:
        return FailingCommitUnitOfWork(self._catalog, self._bindings, self._upstreams)


@pytest.mark.asyncio
async def test_commit_failure_rolls_back_every_pending_state_change() -> None:
    previous = _version("version-1", 1, ToolVersionStatus.PUBLISHED)
    previous_binding = _binding("binding-1", "version-1", ToolBindingStatus.PUBLISHED)
    target = _version()
    target_binding = _binding()
    catalog = InMemoryToolCatalogRepository(
        tools=[_tool()],
        versions=[previous, target],
    )
    bindings = InMemoryToolBindingRepository([previous_binding, target_binding])
    upstreams = InMemoryUpstreamRepository([_upstream()])
    use_case = PublishTool(
        FailingCommitFactory(catalog, bindings, upstreams),
        FixedClock(NOW),
    )

    with pytest.raises(RuntimeError, match="commit failure"):
        await use_case.execute(_command(target, target_binding))

    assert (
        await catalog.get_version_by_id(TENANT_ID, previous.id)
    ).status is ToolVersionStatus.PUBLISHED  # type: ignore[union-attr]
    assert (
        await catalog.get_version_by_id(TENANT_ID, target.id)
    ).status is ToolVersionStatus.REVIEW  # type: ignore[union-attr]
    assert (
        await bindings.get_by_id(TENANT_ID, previous_binding.id)
    ).status is ToolBindingStatus.PUBLISHED  # type: ignore[union-attr]
    assert (
        await bindings.get_by_id(TENANT_ID, target_binding.id)
    ).status is ToolBindingStatus.DRAFT  # type: ignore[union-attr]
