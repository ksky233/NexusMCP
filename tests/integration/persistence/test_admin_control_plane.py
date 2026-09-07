"""Admin REST → PostgreSQL → MCP tools/list 的 S2 Control Plane 总验收。"""

import uuid
from pathlib import Path

import httpx2
import pytest
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from nexusmcp.bootstrap.app import create_app
from nexusmcp.bootstrap.config import Settings
from nexusmcp.modules.identity.adapters.sqlalchemy_models import TenantModel
from tests.contract.repositories.contracts import TENANT_A_ID

pytestmark = pytest.mark.integration

UPSTREAM_ROOT = Path(__file__).resolve().parents[3] / "examples" / "upstream_apis"


async def seed_tenant(session: AsyncSession) -> None:
    session.add(
        TenantModel(
            id=uuid.UUID(TENANT_A_ID),
            name="Admin Control Plane Tenant",
            status="active",
        )
    )
    await session.commit()


@pytest.mark.asyncio
async def test_admin_rest_drives_import_review_publish_search_and_mcp(
    pg_session_factory: async_sessionmaker[AsyncSession],
    migrated_database_url: str,
) -> None:
    async with pg_session_factory() as seed_session:
        await seed_tenant(seed_session)
    app = create_app(
        Settings(
            environment="test",
            catalog_backend="postgresql",
            database_url=SecretStr(migrated_database_url),
            local_tenant_id=TENANT_A_ID,
            control_plane_enabled=True,
            local_admin_principal_id="admin-e2e",
            openapi_fixture_root=UPSTREAM_ROOT,
        )
    )

    async with app.router.lifespan_context(app):
        transport = httpx2.ASGITransport(app=app)
        async with httpx2.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            docs = await client.get("/admin/docs")
            assert docs.status_code == 200

            remote_mcp = await client.post(
                "/admin/upstreams",
                json={
                    "namespace": "remote",
                    "name": "unsupported-remote-mcp",
                    "owner": "platform-team",
                    "endpoint": "https://mcp.example.test/mcp",
                    "service_type": "remote_mcp",
                    "transport_type": "streamable_http",
                },
            )
            assert remote_mcp.status_code == 501
            assert remote_mcp.headers["content-type"].startswith("application/problem+json")
            assert remote_mcp.json()["code"] == "feature_not_enabled"

            invalid_upstream = await client.post(
                "/admin/upstreams",
                json={
                    "namespace": "directory",
                    "name": "missing-owner",
                    "endpoint": "http://127.0.0.1:9001",
                },
            )
            assert invalid_upstream.status_code == 422
            assert invalid_upstream.json()["code"] == "request_validation_failed"
            assert invalid_upstream.json()["errors"][0]["field"] == "owner"

            register = await client.post(
                "/admin/upstreams",
                headers={"X-NexusMCP-Tenant-ID": "forged-tenant"},
                json={
                    "namespace": "directory",
                    "name": "employee-directory-api",
                    "description": "Employee Directory",
                    "owner": "people-platform",
                    "endpoint": "http://127.0.0.1:9001",
                    "auth_scheme": "none",
                    "config": {"timeout_seconds": 5},
                },
            )
            assert register.status_code == 201
            assert "X-Request-ID" in register.headers
            upstream_id = register.json()["id"]
            assert register.json()["tenant_id"] == TENANT_A_ID

            duplicate = await client.post(
                "/admin/upstreams",
                json={
                    "namespace": "directory",
                    "name": "employee-directory-api",
                    "owner": "people-platform",
                    "endpoint": "http://127.0.0.1:9001",
                },
            )
            assert duplicate.status_code == 409
            assert duplicate.json()["code"] == "upstream_conflict"
            assert duplicate.json()["status"] == 409
            assert duplicate.headers["content-type"].startswith("application/problem+json")

            update = await client.put(
                f"/admin/upstreams/{upstream_id}",
                json={
                    "description": "Updated Employee Directory",
                    "owner": "platform-team",
                    "endpoint": "http://127.0.0.1:9011",
                    "auth_scheme": "none",
                    "config": {"timeout_seconds": 10},
                },
            )
            assert update.status_code == 200
            assert update.json()["owner"] == "platform-team"

            upstreams = await client.get("/admin/upstreams")
            assert [item["id"] for item in upstreams.json()["items"]] == [upstream_id]
            assert upstreams.json()["page"] == {"offset": 0, "limit": 50, "total": 1}

            empty_page = await client.get("/admin/upstreams", params={"offset": 1, "limit": 1})
            assert empty_page.json() == {
                "items": [],
                "page": {"offset": 1, "limit": 1, "total": 1},
            }

            submitted_import = await client.post(
                "/admin/openapi/imports",
                json={
                    "upstream_service_id": upstream_id,
                    "source_ref": "employee_directory/openapi.json",
                },
            )
            assert submitted_import.status_code == 202
            import_job_id = submitted_import.json()["import_job_id"]

            import_detail = await client.get(f"/admin/openapi/imports/{import_job_id}")
            assert import_detail.status_code == 200
            assert import_detail.json()["job"]["status"] == "completed"
            operations = import_detail.json()["operations"]
            get_employee = next(
                operation for operation in operations if operation["operation_id"] == "getEmployee"
            )

            reviewed = await client.post(
                f"/admin/openapi/operations/{get_employee['id']}/review",
                json={"owner": "people-platform", "visibility": "public"},
            )
            assert reviewed.status_code == 200
            review_data = reviewed.json()
            assert review_data["canonical_name"] == "directory.get_employee"

            submitted_review = await client.post(
                f"/admin/tool-versions/{review_data['tool_version_id']}/submit-review"
            )
            assert submitted_review.status_code == 200
            assert submitted_review.json() == {"status": "review"}

            published = await client.post(
                "/admin/tools/"
                f"{review_data['tool_id']}/versions/{review_data['tool_version_id']}/publish",
                json={
                    "expected_schema_digest": review_data["schema_digest"],
                    "expected_binding_digest": review_data["binding_digest"],
                },
            )
            assert published.status_code == 200
            assert published.json()["canonical_name"] == "directory.get_employee"

            search = await client.get("/admin/catalog/search", params={"q": "employee"})
            assert search.status_code == 200
            assert [item["canonical_name"] for item in search.json()] == ["directory.get_employee"]

            created_toolset = await client.post(
                "/admin/toolsets",
                json={
                    "slug": "people-operations",
                    "name": "People Operations",
                    "description": "Employee directory tools for operations agents.",
                    "discovery_mode": "direct",
                },
            )
            assert created_toolset.status_code == 201
            toolset = created_toolset.json()
            assert toolset["endpoint_path"] == "/mcp/toolsets/people-operations"
            assert toolset["health"] == "unavailable"

            replaced_members = await client.put(
                f"/admin/toolsets/{toolset['id']}/members",
                json={
                    "expected_revision": toolset["revision"],
                    "tool_ids": [review_data["tool_id"]],
                },
            )
            assert replaced_members.status_code == 200
            toolset = replaced_members.json()
            assert toolset["health"] == "healthy"
            assert toolset["available_tool_count"] == 1
            assert toolset["members"][0]["canonical_name"] == "directory.get_employee"
            assert toolset["members"][0]["serialized_schema_size"] > 0

            replaced_grants = await client.put(
                f"/admin/toolsets/{toolset['id']}/grants",
                json={
                    "expected_revision": toolset["revision"],
                    "principal_ids": ["people-agent"],
                },
            )
            toolset = replaced_grants.json()
            assert toolset["principal_ids"] == ["people-agent"]

            activated = await client.post(
                f"/admin/toolsets/{toolset['id']}/activate",
                json={"expected_revision": toolset["revision"]},
            )
            assert activated.status_code == 200
            toolset = activated.json()
            assert toolset["status"] == "active"

            listed_toolsets = await client.get(
                "/admin/toolsets",
                params={"q": "people", "status": "active"},
            )
            assert listed_toolsets.status_code == 200
            assert listed_toolsets.json()["page"]["total"] == 1
            assert listed_toolsets.json()["items"][0]["id"] == toolset["id"]

            stale_update = await client.put(
                f"/admin/toolsets/{toolset['id']}",
                json={
                    "expected_revision": toolset["revision"] - 1,
                    "name": "Stale Update",
                    "description": None,
                    "discovery_mode": "direct",
                },
            )
            assert stale_update.status_code == 409
            assert stale_update.json()["code"] == "toolset_revision_conflict"

            search_lab = await client.get(
                "/admin/search/tools",
                params={"q": "employee", "retrieval_mode": "lexical"},
            )
            assert search_lab.status_code == 200
            assert search_lab.json()["retrieval_mode"] == "lexical"
            assert search_lab.json()["hits"][0]["canonical_name"] == "directory.get_employee"
            assert search_lab.json()["hits"][0]["input_schema"]["type"] == "object"

            hybrid_unavailable = await client.get(
                "/admin/search/tools",
                params={"q": "find a coworker", "retrieval_mode": "hybrid"},
            )
            assert hybrid_unavailable.status_code == 503
            assert hybrid_unavailable.json()["code"] == "tool_search_mode_unavailable"

            mcp_transport = streamable_http_client(
                "http://testserver/mcp",
                http_client=client,
            )
            async with Client(mcp_transport) as mcp_client:
                tools = await mcp_client.list_tools(cache_mode="refresh")
            assert [tool.name for tool in tools.tools] == [
                "nexus.search_tools",
                "directory.get_employee",
            ]

            disabled = await client.post(f"/admin/upstreams/{upstream_id}/disable")
            assert disabled.status_code == 200
            assert disabled.json()["status"] == "disabled"


@pytest.mark.asyncio
async def test_development_control_plane_bootstraps_its_local_tenant(
    pg_session_factory: async_sessionmaker[AsyncSession],
    migrated_database_url: str,
) -> None:
    app = create_app(
        Settings(
            environment="development",
            catalog_backend="postgresql",
            database_url=SecretStr(migrated_database_url),
            local_tenant_id=TENANT_A_ID,
            control_plane_enabled=True,
        )
    )

    async with app.router.lifespan_context(app):
        async with httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            response = await client.post(
                "/admin/upstreams",
                json={
                    "namespace": "local_directory",
                    "name": "employee-directory-local",
                    "owner": "people-platform",
                    "endpoint": "http://127.0.0.1:9001",
                },
            )

    assert response.status_code == 201
    async with pg_session_factory() as session:
        tenant = await session.get(TenantModel, uuid.UUID(TENANT_A_ID))
    assert tenant is not None
    assert tenant.name == "Local Development Tenant"
