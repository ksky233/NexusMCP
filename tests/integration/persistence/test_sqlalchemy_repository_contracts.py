"""PostgreSQL Adapter 对共享 Repository/UoW Contract 的实现与数据库专有行为。"""

import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from nexusmcp.modules.catalog.adapters.sqlalchemy_mapping import (
    tool_to_model,
    tool_version_to_model,
)
from nexusmcp.modules.catalog.adapters.sqlalchemy_repository import (
    SqlAlchemyToolCatalogRepository,
)
from nexusmcp.modules.catalog.adapters.sqlalchemy_uow import (
    SqlAlchemyCatalogUnitOfWorkFactory,
)
from nexusmcp.modules.catalog.ports import (
    CatalogUnitOfWork,
    CatalogUnitOfWorkFactory,
    ToolCatalogRepository,
)
from nexusmcp.modules.connectors.adapters.sqlalchemy_mapping import tool_binding_to_model
from nexusmcp.modules.connectors.adapters.sqlalchemy_repository import (
    SqlAlchemyToolBindingRepository,
)
from nexusmcp.modules.connectors.ports import ToolBindingRepository
from nexusmcp.modules.identity.adapters.sqlalchemy_models import TenantModel
from nexusmcp.modules.registry.adapters.sqlalchemy_models import UpstreamServiceModel
from tests.contract.repositories.contracts import (
    NOW,
    TENANT_A_ID,
    TOOL_ID,
    UPSTREAM_ID,
    CatalogRepositoryContract,
    CatalogUnitOfWorkContract,
    ToolBindingRepositoryContract,
    make_binding,
    make_tool,
    make_version,
)

pytestmark = pytest.mark.integration


async def seed_tenant_and_upstream(session: AsyncSession) -> None:
    tenant_uuid = uuid.UUID(TENANT_A_ID)
    session.add(
        TenantModel(
            id=tenant_uuid,
            name="Contract Tenant A",
            status="active",
        )
    )
    await session.flush()
    session.add(
        UpstreamServiceModel(
            id=uuid.UUID(UPSTREAM_ID),
            tenant_id=tenant_uuid,
            namespace="directory",
            name="employee-directory",
            description="Repository contract upstream",
            owner="people-platform",
            service_type="http",
            transport_type="http",
            endpoint="http://127.0.0.1:9001",
            auth_scheme="none",
            config_json={},
            status="active",
        )
    )
    await session.flush()


async def seed_tool_and_version(session: AsyncSession) -> None:
    session.add(tool_to_model(make_tool()))
    await session.flush()
    session.add(tool_version_to_model(make_version()))
    await session.flush()


async def seed_published_catalog(session: AsyncSession) -> None:
    session.add(tool_to_model(make_tool()))
    await session.flush()
    published_version = make_version().submit_for_review(NOW).publish(NOW)
    session.add(tool_version_to_model(published_version))
    await session.flush()
    published_binding = make_binding().publish(NOW)
    session.add(tool_binding_to_model(published_binding))
    await session.flush()


class TestSqlAlchemyToolCatalogRepository(CatalogRepositoryContract):
    @pytest_asyncio.fixture
    async def empty_catalog(
        self,
        pg_session_factory: async_sessionmaker[AsyncSession],
    ) -> AsyncIterator[ToolCatalogRepository]:
        async with pg_session_factory() as session:
            await seed_tenant_and_upstream(session)
            await session.commit()
            yield SqlAlchemyToolCatalogRepository(session)

    @pytest_asyncio.fixture
    async def published_catalog(
        self,
        pg_session_factory: async_sessionmaker[AsyncSession],
    ) -> AsyncIterator[ToolCatalogRepository]:
        async with pg_session_factory() as session:
            await seed_tenant_and_upstream(session)
            await seed_published_catalog(session)
            await session.commit()
            yield SqlAlchemyToolCatalogRepository(session)


class TestSqlAlchemyToolBindingRepository(ToolBindingRepositoryContract):
    @pytest_asyncio.fixture
    async def empty_bindings(
        self,
        pg_session_factory: async_sessionmaker[AsyncSession],
    ) -> AsyncIterator[ToolBindingRepository]:
        async with pg_session_factory() as session:
            await seed_tenant_and_upstream(session)
            await seed_tool_and_version(session)
            await session.commit()
            yield SqlAlchemyToolBindingRepository(session)


class TestSqlAlchemyCatalogUnitOfWork(CatalogUnitOfWorkContract):
    @pytest_asyncio.fixture
    async def unit_of_work_bundle(
        self,
        pg_session_factory: async_sessionmaker[AsyncSession],
    ) -> AsyncIterator[tuple[CatalogUnitOfWork, ToolCatalogRepository, ToolBindingRepository]]:
        async with pg_session_factory() as seed_session:
            await seed_tenant_and_upstream(seed_session)
            await seed_session.commit()

        async with pg_session_factory() as observer_session:
            yield (
                SqlAlchemyCatalogUnitOfWorkFactory(pg_session_factory)(),
                SqlAlchemyToolCatalogRepository(observer_session),
                SqlAlchemyToolBindingRepository(observer_session),
            )


@pytest.mark.asyncio
async def test_published_projection_requires_published_binding(
    pg_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with pg_session_factory() as session:
        await seed_tenant_and_upstream(session)
        session.add(tool_to_model(make_tool()))
        await session.flush()
        published_version = make_version().submit_for_review(NOW).publish(NOW)
        session.add(tool_version_to_model(published_version))
        await session.flush()
        draft_binding = make_binding()
        session.add(tool_binding_to_model(draft_binding))
        await session.commit()
        repository = SqlAlchemyToolCatalogRepository(session)

        assert await repository.list_published_by_tenant(TENANT_A_ID) == ()

        binding_repository = SqlAlchemyToolBindingRepository(session)
        await binding_repository.save(TENANT_A_ID, draft_binding.publish(NOW))

        tools = await repository.list_published_by_tenant(TENANT_A_ID)
        assert [tool.canonical_name for tool in tools] == ["directory.get_employee"]


@pytest.mark.asyncio
async def test_get_tool_for_update_acquires_postgresql_row_lock(
    pg_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with pg_session_factory() as seed_session:
        await seed_tenant_and_upstream(seed_session)
        seed_session.add(tool_to_model(make_tool()))
        await seed_session.commit()

    async with pg_session_factory() as first_session, pg_session_factory() as second_session:
        first_repository = SqlAlchemyToolCatalogRepository(first_session)
        second_repository = SqlAlchemyToolCatalogRepository(second_session)

        locked = await first_repository.get_tool_for_update(TENANT_A_ID, TOOL_ID)
        assert locked is not None

        await second_session.execute(text("SET LOCAL lock_timeout = '100ms'"))
        with pytest.raises(DBAPIError):
            await second_repository.get_tool_for_update(TENANT_A_ID, TOOL_ID)

        await second_session.rollback()
        await first_session.rollback()


@pytest.mark.asyncio
async def test_sqlalchemy_uow_uses_one_session_per_factory_call(
    pg_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    # Factory 只持有 Session 配置，不提前创建或共享正在使用的 Session。
    factory: CatalogUnitOfWorkFactory = SqlAlchemyCatalogUnitOfWorkFactory(pg_session_factory)
    first = factory()
    second = factory()
    assert first is not second


def test_contract_uses_uuid_compatible_ids() -> None:
    assert uuid.UUID(TENANT_A_ID)
    assert uuid.UUID(TOOL_ID)
