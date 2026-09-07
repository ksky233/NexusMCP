"""PostgreSQL FTS 排名、Tenant、生命周期与 Visibility Integration Test。"""

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from nexusmcp.infrastructure.persistence.runtime import DatabaseRuntime
from nexusmcp.modules.catalog.adapters.sqlalchemy_models import ToolModel
from nexusmcp.modules.catalog.adapters.sqlalchemy_repository import (
    SqlAlchemyToolCatalogRepository,
)
from nexusmcp.modules.catalog.adapters.sqlalchemy_search import SqlAlchemyPublishedToolSearch
from nexusmcp.modules.catalog.domain import (
    Tool,
    ToolSideEffect,
    ToolStatus,
    ToolVersion,
    ToolVersionStatus,
    ToolVisibility,
)
from nexusmcp.modules.catalog.search import SearchPublishedTools, SearchPublishedToolsQuery
from nexusmcp.modules.connectors.adapters.sqlalchemy_repository import (
    SqlAlchemyToolBindingRepository,
)
from nexusmcp.modules.connectors.domain import (
    ToolBinding,
    ToolBindingStatus,
    ToolBindingType,
)
from nexusmcp.modules.identity.adapters.sqlalchemy_models import TenantModel
from nexusmcp.modules.registry.adapters.sqlalchemy_models import UpstreamServiceModel
from nexusmcp.shared.request_context import ProtocolEra, RequestContext
from tests.contract.repositories.contracts import TENANT_A_ID, TENANT_B_ID

pytestmark = pytest.mark.integration

NOW = datetime(2026, 8, 26, 10, 0, tzinfo=UTC)
UPSTREAM_A_ID = "00000000-0000-0000-0000-000000000501"
UPSTREAM_B_ID = "00000000-0000-0000-0000-000000000502"


def context(tenant_id: str, principal_id: str) -> RequestContext:
    return RequestContext(
        request_id=f"request-search-{tenant_id}",
        trace_id="7" * 32,
        protocol_version="2026-07-28",
        protocol_era=ProtocolEra.MODERN,
        tenant_id=tenant_id,
        principal_id=principal_id,
        authn_method="test",
    )


async def seed_tenants_and_upstreams(session: AsyncSession) -> None:
    for tenant_id, suffix, upstream_id in (
        (TENANT_A_ID, "A", UPSTREAM_A_ID),
        (TENANT_B_ID, "B", UPSTREAM_B_ID),
    ):
        tenant_uuid = uuid.UUID(tenant_id)
        session.add(TenantModel(id=tenant_uuid, name=f"Search Tenant {suffix}", status="active"))
        await session.flush()
        session.add(
            UpstreamServiceModel(
                id=uuid.UUID(upstream_id),
                tenant_id=tenant_uuid,
                namespace="inventory",
                name=f"inventory-search-{suffix.lower()}",
                description="FTS integration upstream",
                owner="search-test",
                service_type="http",
                transport_type="http",
                endpoint=("http://127.0.0.1:9101" if suffix == "A" else "http://127.0.0.1:9102"),
                auth_scheme="none",
                config_json={},
                status="active",
            )
        )
        await session.flush()


async def add_catalog_tool(
    session: AsyncSession,
    *,
    tenant_id: str,
    upstream_id: str,
    canonical_name: str,
    display_name: str,
    description: str,
    tags: tuple[str, ...],
    tool_status: ToolStatus = ToolStatus.ACTIVE,
    version_status: ToolVersionStatus = ToolVersionStatus.PUBLISHED,
    binding_status: ToolBindingStatus = ToolBindingStatus.PUBLISHED,
    visibility: ToolVisibility = ToolVisibility.PUBLIC,
) -> None:
    tool_id = str(uuid.uuid4())
    version_id = str(uuid.uuid4())
    tool = Tool(
        id=tool_id,
        tenant_id=tenant_id,
        namespace="inventory",
        canonical_name=canonical_name,
        owner="search-test",
        status=tool_status,
    )
    version = ToolVersion(
        id=version_id,
        tenant_id=tenant_id,
        tool_id=tool_id,
        version=1,
        display_name=display_name,
        description=description,
        input_schema={"type": "object", "properties": {}},
        output_schema=None,
        schema_digest=uuid.uuid4().hex * 2,
        tags=tags,
        side_effect=ToolSideEffect.READ_ONLY,
        visibility=visibility,
        status=version_status,
        created_by="search-test",
        created_at=NOW,
        reviewed_at=NOW if version_status is not ToolVersionStatus.DRAFT else None,
        published_at=NOW if version_status is ToolVersionStatus.PUBLISHED else None,
    )
    binding = ToolBinding(
        id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        tool_version_id=version_id,
        upstream_service_id=upstream_id,
        imported_operation_id=None,
        binding_type=ToolBindingType.HTTP,
        binding_config={"method": "GET", "path_template": "/search-test"},
        binding_digest=uuid.uuid4().hex * 2,
        status=binding_status,
        created_at=NOW,
        published_at=NOW if binding_status is ToolBindingStatus.PUBLISHED else None,
    )
    catalog = SqlAlchemyToolCatalogRepository(session)
    await catalog.add_tool(tenant_id, tool)
    await catalog.add_version(tenant_id, version)
    await SqlAlchemyToolBindingRepository(session).add(tenant_id, binding)


async def seed_search_catalog(session: AsyncSession) -> None:
    await seed_tenants_and_upstreams(session)
    await add_catalog_tool(
        session,
        tenant_id=TENANT_A_ID,
        upstream_id=UPSTREAM_A_ID,
        canonical_name="inventory.reserve_stock",
        display_name="Reserve stock",
        description="Create a reservation for one warehouse order.",
        tags=("inventory", "warehouse", "write"),
    )
    await add_catalog_tool(
        session,
        tenant_id=TENANT_A_ID,
        upstream_id=UPSTREAM_A_ID,
        canonical_name="inventory.get_status",
        display_name="Get availability",
        description="Inspect current stock availability in one warehouse.",
        tags=("inventory", "read"),
    )
    await add_catalog_tool(
        session,
        tenant_id=TENANT_A_ID,
        upstream_id=UPSTREAM_A_ID,
        canonical_name="inventory.draft_forecast",
        display_name="Draft forecast",
        description="Forecast future stock demand.",
        tags=("inventory",),
        version_status=ToolVersionStatus.DRAFT,
        binding_status=ToolBindingStatus.DRAFT,
    )
    await add_catalog_tool(
        session,
        tenant_id=TENANT_A_ID,
        upstream_id=UPSTREAM_A_ID,
        canonical_name="inventory.disabled_adjustment",
        display_name="Disabled stock adjustment",
        description="Adjust stock in a warehouse.",
        tags=("inventory",),
        tool_status=ToolStatus.DISABLED,
    )
    await add_catalog_tool(
        session,
        tenant_id=TENANT_A_ID,
        upstream_id=UPSTREAM_A_ID,
        canonical_name="inventory.internal_reconciliation",
        display_name="Internal reconciliation",
        description="Run internal stock reconciliation.",
        tags=("inventory", "internal"),
        visibility=ToolVisibility.AUTHENTICATED,
    )
    await add_catalog_tool(
        session,
        tenant_id=TENANT_A_ID,
        upstream_id=UPSTREAM_A_ID,
        canonical_name="inventory.restricted_audit",
        display_name="Restricted stock audit",
        description="Audit restricted stock records.",
        tags=("inventory", "audit"),
        visibility=ToolVisibility.RESTRICTED,
    )
    await add_catalog_tool(
        session,
        tenant_id=TENANT_B_ID,
        upstream_id=UPSTREAM_B_ID,
        canonical_name="inventory.cross_tenant_stock",
        display_name="Cross tenant stock",
        description="Stock data owned by another tenant.",
        tags=("inventory",),
    )
    await session.commit()


@pytest.mark.asyncio
async def test_fts_ranking_and_governance_filters(
    pg_session_factory: async_sessionmaker[AsyncSession],
    migrated_database_url: str,
) -> None:
    async with pg_session_factory() as seed_session:
        await seed_search_catalog(seed_session)
        scoped_tool_id = str(
            await seed_session.scalar(
                select(ToolModel.id).where(ToolModel.canonical_name == "inventory.get_status")
            )
        )
    runtime = DatabaseRuntime(migrated_database_url)
    await runtime.start()
    try:
        use_case = SearchPublishedTools(SqlAlchemyPublishedToolSearch(runtime))
        anonymous_stock = await use_case.execute(
            SearchPublishedToolsQuery(
                context=context(TENANT_A_ID, "anonymous"),
                text="stock",
            )
        )
        authenticated_internal = await use_case.execute(
            SearchPublishedToolsQuery(
                context=context(TENANT_A_ID, "operator"),
                text="reconciliation",
            )
        )
        anonymous_internal = await use_case.execute(
            SearchPublishedToolsQuery(
                context=context(TENANT_A_ID, "anonymous"),
                text="reconciliation",
            )
        )
        tenant_b = await use_case.execute(
            SearchPublishedToolsQuery(
                context=context(TENANT_B_ID, "operator"),
                text="stock",
            )
        )
        limited = await use_case.execute(
            SearchPublishedToolsQuery(
                context=context(TENANT_A_ID, "operator"),
                text="inventory",
                limit=1,
            )
        )
        scoped = await use_case.execute(
            SearchPublishedToolsQuery(
                context=context(TENANT_A_ID, "operator"),
                text="inventory",
                eligible_tool_ids=(scoped_tool_id,),
            )
        )
        empty_scope = await use_case.execute(
            SearchPublishedToolsQuery(
                context=context(TENANT_A_ID, "operator"),
                text="inventory",
                eligible_tool_ids=(),
            )
        )
    finally:
        await runtime.stop()

    assert [hit.tool.canonical_name for hit in anonymous_stock] == [
        "inventory.reserve_stock",
        "inventory.get_status",
    ]
    assert anonymous_stock[0].rank > anonymous_stock[1].rank > 0
    assert [hit.tool.canonical_name for hit in authenticated_internal] == [
        "inventory.internal_reconciliation"
    ]
    assert anonymous_internal == ()
    assert [hit.tool.canonical_name for hit in tenant_b] == ["inventory.cross_tenant_stock"]
    assert len(limited) == 1
    assert [hit.tool.canonical_name for hit in scoped] == ["inventory.get_status"]
    assert empty_scope == ()
