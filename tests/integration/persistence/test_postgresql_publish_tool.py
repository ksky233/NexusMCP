"""Publish Use Case 的真实 PostgreSQL 原子事务与 Tenant 边界测试。"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, replace
from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from nexusmcp.modules.catalog.adapters.sqlalchemy_mapping import (
    tool_to_model,
    tool_version_to_model,
)
from nexusmcp.modules.catalog.adapters.sqlalchemy_repository import (
    SqlAlchemyToolCatalogRepository,
)
from nexusmcp.modules.catalog.adapters.sqlalchemy_uow import (
    SqlAlchemyCatalogUnitOfWork,
    SqlAlchemyCatalogUnitOfWorkFactory,
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
from nexusmcp.modules.connectors.adapters.sqlalchemy_mapping import tool_binding_to_model
from nexusmcp.modules.connectors.adapters.sqlalchemy_repository import (
    SqlAlchemyToolBindingRepository,
)
from nexusmcp.modules.connectors.digests import calculate_binding_digest
from nexusmcp.modules.connectors.domain import (
    ToolBinding,
    ToolBindingStatus,
    ToolBindingType,
)
from nexusmcp.modules.identity.adapters.sqlalchemy_models import TenantModel
from nexusmcp.modules.registry.adapters.sqlalchemy_models import UpstreamServiceModel
from nexusmcp.shared.errors import TenantBoundaryViolationError
from nexusmcp.shared.request_context import ProtocolEra, RequestContext
from tests.contract.repositories.contracts import (
    BINDING_ID,
    PUBLISHED_VERSION_ID,
    TENANT_A_ID,
    TENANT_B_ID,
    TOOL_ID,
    UPSTREAM_ID,
    VERSION_ID,
)

pytestmark = pytest.mark.integration

TARGET_BINDING_ID = "00000000-0000-0000-0000-000000000302"
NOW = datetime(2026, 8, 25, 11, 0, tzinfo=UTC)


@dataclass(frozen=True, slots=True)
class FixedClock:
    value: datetime

    def now(self) -> datetime:
        return self.value


def make_context() -> RequestContext:
    return RequestContext(
        request_id="request-postgresql-publish",
        trace_id="2" * 32,
        protocol_version="2026-07-28",
        protocol_era=ProtocolEra.MODERN,
        tenant_id=TENANT_A_ID,
        principal_id="publisher-postgresql",
        authn_method="test",
    )


def make_tool() -> Tool:
    return Tool(
        id=TOOL_ID,
        tenant_id=TENANT_A_ID,
        namespace="directory",
        canonical_name="directory.get_employee",
        owner="people-platform",
        status=ToolStatus.DISABLED,
    )


def make_version(
    version_id: str,
    version_number: int,
    status: ToolVersionStatus,
) -> ToolVersion:
    input_schema = {
        "type": "object",
        "properties": {"employee_id": {"type": "string"}},
        "required": ["employee_id"],
    }
    return ToolVersion(
        id=version_id,
        tenant_id=TENANT_A_ID,
        tool_id=TOOL_ID,
        version=version_number,
        display_name=f"Get employee v{version_number}",
        description="Get one employee by id.",
        input_schema=input_schema,
        output_schema=None,
        schema_digest=calculate_schema_digest(input_schema, None),
        tags=("directory",),
        side_effect=ToolSideEffect.READ_ONLY,
        visibility=ToolVisibility.PUBLIC,
        status=status,
        created_by="reviewer-postgresql",
        created_at=NOW,
        reviewed_at=NOW,
        published_at=NOW if status is ToolVersionStatus.PUBLISHED else None,
    )


def make_binding(
    binding_id: str,
    version_id: str,
    status: ToolBindingStatus,
) -> ToolBinding:
    binding = ToolBinding(
        id=binding_id,
        tenant_id=TENANT_A_ID,
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


async def seed_publish_aggregate(
    session: AsyncSession,
    *,
    include_previous: bool,
    upstream_tenant_id: str = TENANT_A_ID,
) -> tuple[ToolVersion, ToolBinding]:
    session.add(
        TenantModel(
            id=uuid.UUID(TENANT_A_ID),
            name="Publish Tenant A",
            status="active",
        )
    )
    if upstream_tenant_id == TENANT_B_ID:
        session.add(
            TenantModel(
                id=uuid.UUID(TENANT_B_ID),
                name="Publish Tenant B",
                status="active",
            )
        )
    await session.flush()
    session.add(
        UpstreamServiceModel(
            id=uuid.UUID(UPSTREAM_ID),
            tenant_id=uuid.UUID(upstream_tenant_id),
            namespace="directory",
            name="employee-directory",
            description="Publish integration upstream",
            owner="people-platform",
            service_type="http",
            transport_type="http",
            endpoint="http://127.0.0.1:9001",
            auth_scheme="none",
            config_json={},
            status="active",
        )
    )
    session.add(tool_to_model(make_tool()))
    await session.flush()

    if include_previous:
        previous = make_version(VERSION_ID, 1, ToolVersionStatus.PUBLISHED)
        previous_binding = make_binding(BINDING_ID, VERSION_ID, ToolBindingStatus.PUBLISHED)
        session.add(tool_version_to_model(previous))
        await session.flush()
        session.add(tool_binding_to_model(previous_binding))
        await session.flush()

    target_version_number = 2 if include_previous else 1
    target = make_version(
        PUBLISHED_VERSION_ID,
        target_version_number,
        ToolVersionStatus.REVIEW,
    )
    target_binding = make_binding(
        TARGET_BINDING_ID,
        PUBLISHED_VERSION_ID,
        ToolBindingStatus.DRAFT,
    )
    session.add(tool_version_to_model(target))
    await session.flush()
    session.add(tool_binding_to_model(target_binding))
    await session.commit()
    return target, target_binding


def make_command(version: ToolVersion, binding: ToolBinding) -> PublishToolCommand:
    return PublishToolCommand(
        context=make_context(),
        tool_id=TOOL_ID,
        tool_version_id=version.id,
        expected_schema_digest=version.schema_digest,
        expected_binding_digest=binding.binding_digest,
    )


@pytest.mark.asyncio
async def test_postgresql_publish_switches_version_and_binding_atomically(
    pg_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with pg_session_factory() as seed_session:
        target, target_binding = await seed_publish_aggregate(
            seed_session,
            include_previous=True,
        )
    use_case = PublishTool(
        SqlAlchemyCatalogUnitOfWorkFactory(pg_session_factory),
        FixedClock(NOW),
    )

    result = await use_case.execute(make_command(target, target_binding))

    async with pg_session_factory() as observer_session:
        catalog = SqlAlchemyToolCatalogRepository(observer_session)
        bindings = SqlAlchemyToolBindingRepository(observer_session)
        previous = await catalog.get_version_by_id(TENANT_A_ID, VERSION_ID)
        published = await catalog.get_version_by_id(TENANT_A_ID, PUBLISHED_VERSION_ID)
        previous_binding = await bindings.get_by_id(TENANT_A_ID, BINDING_ID)
        published_binding = await bindings.get_by_id(TENANT_A_ID, TARGET_BINDING_ID)
        tool = await catalog.get_tool_by_id(TENANT_A_ID, TOOL_ID)
        projections = await catalog.list_published_by_tenant(TENANT_A_ID)

    assert previous is not None and previous.status is ToolVersionStatus.RETIRED
    assert published is not None and published.status is ToolVersionStatus.PUBLISHED
    assert previous_binding is not None
    assert previous_binding.status is ToolBindingStatus.DISABLED
    assert published_binding is not None
    assert published_binding.status is ToolBindingStatus.PUBLISHED
    assert tool is not None and tool.status is ToolStatus.ACTIVE
    assert [projection.tool_version_id for projection in projections] == [PUBLISHED_VERSION_ID]
    assert result.retired_tool_version_id == VERSION_ID


class FailingCommitUnitOfWork(SqlAlchemyCatalogUnitOfWork):
    async def __aenter__(self) -> FailingCommitUnitOfWork:
        await super().__aenter__()
        return self

    async def commit(self) -> None:
        raise RuntimeError("simulated post-flush commit failure")


class FailingCommitFactory:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    def __call__(self) -> FailingCommitUnitOfWork:
        return FailingCommitUnitOfWork(self._session_factory)


@pytest.mark.asyncio
async def test_postgresql_commit_failure_rolls_back_retire_and_publish_flushes(
    pg_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with pg_session_factory() as seed_session:
        target, target_binding = await seed_publish_aggregate(
            seed_session,
            include_previous=True,
        )
    use_case = PublishTool(FailingCommitFactory(pg_session_factory), FixedClock(NOW))

    with pytest.raises(RuntimeError, match="post-flush commit failure"):
        await use_case.execute(make_command(target, target_binding))

    async with pg_session_factory() as observer_session:
        catalog = SqlAlchemyToolCatalogRepository(observer_session)
        bindings = SqlAlchemyToolBindingRepository(observer_session)
        previous = await catalog.get_version_by_id(TENANT_A_ID, VERSION_ID)
        target_after_failure = await catalog.get_version_by_id(
            TENANT_A_ID,
            PUBLISHED_VERSION_ID,
        )
        previous_binding = await bindings.get_by_id(TENANT_A_ID, BINDING_ID)
        target_binding_after_failure = await bindings.get_by_id(
            TENANT_A_ID,
            TARGET_BINDING_ID,
        )

    assert previous is not None and previous.status is ToolVersionStatus.PUBLISHED
    assert target_after_failure is not None
    assert target_after_failure.status is ToolVersionStatus.REVIEW
    assert previous_binding is not None
    assert previous_binding.status is ToolBindingStatus.PUBLISHED
    assert target_binding_after_failure is not None
    assert target_binding_after_failure.status is ToolBindingStatus.DRAFT


@pytest.mark.asyncio
async def test_postgresql_rejects_cross_tenant_upstream_binding_before_publish(
    pg_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with pg_session_factory() as seed_session:
        target, target_binding = await seed_publish_aggregate(
            seed_session,
            include_previous=False,
            upstream_tenant_id=TENANT_B_ID,
        )
    use_case = PublishTool(
        SqlAlchemyCatalogUnitOfWorkFactory(pg_session_factory),
        FixedClock(NOW),
    )

    with pytest.raises(TenantBoundaryViolationError):
        await use_case.execute(make_command(target, target_binding))

    async with pg_session_factory() as observer_session:
        catalog = SqlAlchemyToolCatalogRepository(observer_session)
        bindings = SqlAlchemyToolBindingRepository(observer_session)
        target_after_failure = await catalog.get_version_by_id(
            TENANT_A_ID,
            PUBLISHED_VERSION_ID,
        )
        binding_after_failure = await bindings.get_by_id(
            TENANT_A_ID,
            TARGET_BINDING_ID,
        )

    assert target_after_failure is not None
    assert target_after_failure.status is ToolVersionStatus.REVIEW
    assert binding_after_failure is not None
    assert binding_after_failure.status is ToolBindingStatus.DRAFT
