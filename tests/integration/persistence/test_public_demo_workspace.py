"""Public Demo Tenant Bootstrap 与工作区重置集成测试。"""

import uuid

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from nexusmcp.bootstrap.app import create_app
from nexusmcp.bootstrap.config import Settings
from nexusmcp.modules.identity.adapters.sqlalchemy_models import TenantModel
from nexusmcp.modules.toolsets.adapters.sqlalchemy_models import (
    ToolsetAccessGrantModel,
    ToolsetModel,
)
from tests.contract.repositories.contracts import TENANT_A_ID

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_public_demo_bootstraps_tenant_and_resets_business_workspace(
    pg_session_factory: async_sessionmaker[AsyncSession],
    migrated_database_url: str,
) -> None:
    app = create_app(
        Settings(
            environment="test",
            catalog_backend="postgresql",
            database_url=SecretStr(migrated_database_url),
            local_tenant_id=TENANT_A_ID,
            control_plane_enabled=True,
            admin_identity_mode="public_demo",
            demo_admin_principal_id="public-demo-admin",
            static_agent_principal_id="public-demo-agent",
            embedding_api_key=None,
        )
    )

    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            registered = await client.post(
                "/admin/upstreams",
                json={
                    "namespace": "directory",
                    "name": "employee-directory-demo",
                    "owner": "people-platform",
                    "endpoint": "http://demo-upstreams:9000/employee-directory",
                },
            )
            assert registered.status_code == 201

            reset = await client.post("/admin/demo/reset")
            assert reset.status_code == 200
            assert reset.json() == {"status": "reset", "tenant_id": TENANT_A_ID}

            upstreams = await client.get("/admin/upstreams")
            assert upstreams.status_code == 200
            assert upstreams.json()["items"] == []
            assert upstreams.json()["page"]["total"] == 0

    async with pg_session_factory() as session:
        tenant_count = await session.scalar(select(func.count()).select_from(TenantModel))
        tenant = await session.get(TenantModel, uuid.UUID(TENANT_A_ID))
        toolsets = (await session.scalars(select(ToolsetModel))).all()
        grants = (await session.scalars(select(ToolsetAccessGrantModel))).all()

    assert tenant_count == 1
    assert tenant is not None
    assert tenant.name == "NexusMCP Public Demo"
    assert [(toolset.kind, toolset.slug) for toolset in toolsets] == [
        ("all_published", "all-published")
    ]
    assert [grant.principal_id for grant in grants] == ["public-demo-agent"]
