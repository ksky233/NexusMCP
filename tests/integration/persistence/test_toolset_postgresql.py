"""Toolset SQL Catalog Snapshot 与 Execution Scope PostgreSQL 验证。"""

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import text, update
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from nexusmcp.infrastructure.persistence.toolset_uow import (
    SqlAlchemyToolsetUnitOfWorkFactory,
)
from nexusmcp.modules.catalog.adapters.sqlalchemy_models import ToolModel
from nexusmcp.modules.catalog.domain import ToolSideEffect
from nexusmcp.modules.execution.adapters.sqlalchemy_models import ToolExecutionModel
from nexusmcp.modules.execution.adapters.sqlalchemy_repository import (
    SqlAlchemyToolExecutionRepository,
)
from nexusmcp.modules.execution.domain import ExecutionStatus, McpScopeType, ToolExecution
from nexusmcp.modules.toolsets.adapters.sqlalchemy_repository import (
    SqlAlchemyToolsetRepository,
)
from nexusmcp.modules.toolsets.domain import ToolsetMemberAvailability
from tests.contract.repositories.contracts import (
    BINDING_ID,
    TENANT_A_ID,
    TOOL_ID,
    VERSION_ID,
)
from tests.contract.repositories.toolset_contracts import make_toolset
from tests.integration.persistence.test_mcp_read_only_http_call import seed_executable_tool

pytestmark = pytest.mark.integration

DISABLED_TOOL_ID = "00000000-0000-0000-0000-000000000102"
NO_VERSION_TOOL_ID = "00000000-0000-0000-0000-000000000103"
NOW = datetime(2026, 9, 6, 8, 0, tzinfo=UTC)


@pytest.mark.asyncio
async def test_catalog_reader_and_repository_share_one_uow_session_and_classify_tools(
    pg_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with pg_session_factory() as seed_session:
        await seed_executable_tool(seed_session)
        tenant_uuid = uuid.UUID(TENANT_A_ID)
        seed_session.add_all(
            [
                ToolModel(
                    id=uuid.UUID(DISABLED_TOOL_ID),
                    tenant_id=tenant_uuid,
                    namespace="operations",
                    canonical_name="operations.disabled_tool",
                    owner="platform-team",
                    status="disabled",
                ),
                ToolModel(
                    id=uuid.UUID(NO_VERSION_TOOL_ID),
                    tenant_id=tenant_uuid,
                    namespace="operations",
                    canonical_name="operations.no_version",
                    owner="platform-team",
                    status="active",
                ),
            ]
        )
        await seed_session.commit()

    async with SqlAlchemyToolsetUnitOfWorkFactory(pg_session_factory)() as unit_of_work:
        snapshots = await unit_of_work.catalog.list_member_snapshots(
            TENANT_A_ID,
            (NO_VERSION_TOOL_ID, TOOL_ID, DISABLED_TOOL_ID, str(uuid.uuid4())),
        )

    assert [snapshot.tool_id for snapshot in snapshots] == [
        NO_VERSION_TOOL_ID,
        TOOL_ID,
        DISABLED_TOOL_ID,
    ]
    assert [snapshot.availability for snapshot in snapshots] == [
        ToolsetMemberAvailability.NO_PUBLISHED_VERSION,
        ToolsetMemberAvailability.AVAILABLE,
        ToolsetMemberAvailability.TOOL_DISABLED,
    ]
    assert snapshots[1].published_tool_version_id == VERSION_ID


@pytest.mark.asyncio
async def test_execution_scope_round_trips_root_and_toolset_context(
    pg_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with pg_session_factory() as seed_session:
        await seed_executable_tool(seed_session)
        toolset = make_toolset(active=True, principal_ids=("agent-a",))
        await SqlAlchemyToolsetRepository(seed_session).add(TENANT_A_ID, toolset)
        await seed_session.commit()

    root_execution = ToolExecution(
        id="00000000-0000-0000-0000-000000000601",
        tenant_id=TENANT_A_ID,
        request_id="request-root",
        trace_id="a" * 32,
        principal_id="agent-a",
        tool_id=TOOL_ID,
        tool_version_id=VERSION_ID,
        tool_binding_id=BINDING_ID,
        arguments_digest="1" * 64,
        policy_version="policy-v1",
        policy_reason_code="granted_toolset_union",
        side_effect=ToolSideEffect.READ_ONLY,
        status=ExecutionStatus.PLANNED,
        planned_at=NOW,
    )
    scoped_execution = ToolExecution(
        id="00000000-0000-0000-0000-000000000602",
        tenant_id=TENANT_A_ID,
        request_id="request-toolset",
        trace_id="b" * 32,
        principal_id="agent-a",
        tool_id=TOOL_ID,
        tool_version_id=VERSION_ID,
        tool_binding_id=BINDING_ID,
        arguments_digest="2" * 64,
        policy_version="policy-v1",
        policy_reason_code="active_toolset_grant",
        side_effect=ToolSideEffect.READ_ONLY,
        status=ExecutionStatus.PLANNED,
        planned_at=NOW,
        mcp_scope_type=McpScopeType.TOOLSET,
        toolset_id=toolset.id,
        toolset_revision=toolset.revision,
    )

    async with pg_session_factory() as session:
        repository = SqlAlchemyToolExecutionRepository(session)
        await repository.add(TENANT_A_ID, root_execution)
        await repository.add(TENANT_A_ID, scoped_execution)
        await session.commit()
        assert await repository.get_by_id(TENANT_A_ID, root_execution.id) == root_execution
        assert await repository.get_by_id(TENANT_A_ID, scoped_execution.id) == scoped_execution


@pytest.mark.asyncio
async def test_database_rejects_incomplete_toolset_scope(
    pg_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with pg_session_factory() as session:
        await seed_executable_tool(session)
        execution = ToolExecution(
            id="00000000-0000-0000-0000-000000000603",
            tenant_id=TENANT_A_ID,
            request_id="request-invalid-scope",
            trace_id="c" * 32,
            principal_id="agent-a",
            tool_id=TOOL_ID,
            tool_version_id=VERSION_ID,
            tool_binding_id=BINDING_ID,
            arguments_digest="3" * 64,
            policy_version="policy-v1",
            policy_reason_code="root",
            side_effect=ToolSideEffect.READ_ONLY,
            status=ExecutionStatus.PLANNED,
            planned_at=NOW,
        )
        repository = SqlAlchemyToolExecutionRepository(session)
        await repository.add(TENANT_A_ID, execution)
        await session.commit()

        with pytest.raises(IntegrityError):
            await session.execute(
                update(ToolExecutionModel)
                .where(ToolExecutionModel.id == uuid.UUID(execution.id))
                .values(mcp_scope_type="toolset")
            )
            await session.commit()


@pytest.mark.asyncio
async def test_get_toolset_for_update_acquires_postgresql_row_lock(
    pg_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with pg_session_factory() as seed_session:
        await seed_executable_tool(seed_session)
        toolset = make_toolset(active=True)
        await SqlAlchemyToolsetRepository(seed_session).add(TENANT_A_ID, toolset)
        await seed_session.commit()

    async with pg_session_factory() as first_session, pg_session_factory() as second_session:
        first_repository = SqlAlchemyToolsetRepository(first_session)
        second_repository = SqlAlchemyToolsetRepository(second_session)

        locked = await first_repository.get_for_update(TENANT_A_ID, toolset.id)
        assert locked is not None
        await second_session.execute(text("SET LOCAL lock_timeout = '100ms'"))
        with pytest.raises(DBAPIError):
            await second_repository.get_for_update(TENANT_A_ID, toolset.id)
        await second_session.rollback()
        await first_session.rollback()


@pytest.mark.asyncio
async def test_aggregate_replace_rolls_back_or_commits_members_and_grants_atomically(
    pg_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with pg_session_factory() as seed_session:
        await seed_executable_tool(seed_session)
        original = make_toolset(active=True, principal_ids=("agent-a",))
        await SqlAlchemyToolsetRepository(seed_session).add(TENANT_A_ID, original)
        await seed_session.commit()

    factory = SqlAlchemyToolsetUnitOfWorkFactory(pg_session_factory)
    async with factory() as unit_of_work:
        locked = await unit_of_work.toolsets.get_for_update(TENANT_A_ID, original.id)
        assert locked is not None
        replacement = locked.replace_grants(
            expected_revision=locked.revision,
            principal_ids=("agent-b", "agent-c"),
            actor_id="admin-a",
            occurred_at=NOW,
        )
        await unit_of_work.toolsets.save(TENANT_A_ID, replacement)
        # 不调用 commit，退出 UoW 后必须撤销 Aggregate Row、Member 与 Grant 的整体替换。

    async with pg_session_factory() as observer_session:
        rolled_back = await SqlAlchemyToolsetRepository(observer_session).get_by_id(
            TENANT_A_ID, original.id
        )
        assert rolled_back == original

    async with factory() as unit_of_work:
        locked = await unit_of_work.toolsets.get_for_update(TENANT_A_ID, original.id)
        assert locked is not None
        replacement = locked.replace_grants(
            expected_revision=locked.revision,
            principal_ids=("agent-b", "agent-c"),
            actor_id="admin-a",
            occurred_at=NOW,
        )
        await unit_of_work.toolsets.save(TENANT_A_ID, replacement)
        await unit_of_work.commit()

    async with pg_session_factory() as observer_session:
        committed = await SqlAlchemyToolsetRepository(observer_session).get_by_id(
            TENANT_A_ID, original.id
        )
        assert committed == replacement
        assert committed is not None
        assert committed.tool_ids == original.tool_ids
        assert committed.principal_ids == ("agent-b", "agent-c")
