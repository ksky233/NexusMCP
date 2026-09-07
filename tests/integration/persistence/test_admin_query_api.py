"""W1 Admin Query API 的 PostgreSQL、过滤、租户隔离纵向验收。"""

import uuid
from datetime import UTC, datetime, timedelta

import httpx
import httpx2
import pytest
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from examples.upstream_apis.employee_directory.app import app as employee_directory_app
from nexusmcp.bootstrap.app import create_app
from nexusmcp.bootstrap.config import Settings
from nexusmcp.modules.approval.adapters.sqlalchemy_models import ApprovalRequestModel
from nexusmcp.modules.identity.adapters.sqlalchemy_models import TenantModel
from nexusmcp.modules.openapi_import.adapters.sqlalchemy_models import (
    ImportedOperationModel,
    OpenApiImportJobModel,
)
from nexusmcp.modules.registry.adapters.sqlalchemy_models import UpstreamServiceModel
from nexusmcp.modules.tool_search.adapters.sqlalchemy_models import (
    TOOL_EMBEDDING_DIMENSIONS,
    ToolSearchEmbeddingModel,
)
from tests.contract.repositories.contracts import (
    BINDING_ID,
    TENANT_A_ID,
    TENANT_B_ID,
    TOOL_ID,
    UPSTREAM_ID,
    VERSION_ID,
)
from tests.integration.persistence.test_mcp_read_only_http_call import seed_executable_tool

pytestmark = pytest.mark.integration

IMPORT_ID = "00000000-0000-0000-0000-000000000501"
OPERATION_ID = "00000000-0000-0000-0000-000000000601"
APPROVAL_ID = "00000000-0000-0000-0000-000000000701"
EMBEDDING_ID = "00000000-0000-0000-0000-000000000801"
TENANT_B_UPSTREAM_ID = "00000000-0000-0000-0000-000000000402"
NOW = datetime(2026, 8, 28, 9, 0, tzinfo=UTC)


async def seed_admin_query_state(session: AsyncSession) -> None:
    await seed_executable_tool(session, upstream_endpoint="http://127.0.0.1:9001")
    tenant_id = uuid.UUID(TENANT_A_ID)
    session.add_all(
        [
            OpenApiImportJobModel(
                id=uuid.UUID(IMPORT_ID),
                tenant_id=tenant_id,
                upstream_service_id=uuid.UUID(UPSTREAM_ID),
                source_type="local_fixture",
                source_ref="employee_directory/openapi.json",
                source_digest="3" * 64,
                openapi_version="3.1.0",
                operation_allowlist_json=[],
                allowlist_snapshot_json={},
                status="completed",
                error_summary=None,
                created_by="admin-query-test",
                created_at=NOW,
                started_at=NOW,
                completed_at=NOW + timedelta(seconds=1),
            ),
            ApprovalRequestModel(
                id=uuid.UUID(APPROVAL_ID),
                tenant_id=tenant_id,
                principal_id="employee-agent",
                tool_id=uuid.UUID(TOOL_ID),
                tool_version_id=uuid.UUID(VERSION_ID),
                arguments_digest="4" * 64,
                policy_version="policy-v1",
                idempotency_key=None,
                status="pending",
                requested_at=NOW,
                expires_at=NOW + timedelta(minutes=10),
            ),
            ToolSearchEmbeddingModel(
                id=uuid.UUID(EMBEDDING_ID),
                tenant_id=tenant_id,
                tool_version_id=uuid.UUID(VERSION_ID),
                embedding_model="Qwen/Qwen3-Embedding-8B",
                embedding_dimensions=TOOL_EMBEDDING_DIMENSIONS,
                source_digest="5" * 64,
                embedding=[1.0, *([0.0] * (TOOL_EMBEDDING_DIMENSIONS - 1))],
                indexed_at=NOW,
            ),
            TenantModel(
                id=uuid.UUID(TENANT_B_ID),
                name="Hidden Tenant",
                status="active",
            ),
        ]
    )
    await session.flush()
    session.add_all(
        [
            ImportedOperationModel(
                id=uuid.UUID(OPERATION_ID),
                tenant_id=tenant_id,
                import_job_id=uuid.UUID(IMPORT_ID),
                upstream_service_id=uuid.UUID(UPSTREAM_ID),
                operation_key="GET /employees/{employee_id}",
                operation_id="getEmployee",
                method="GET",
                path="/employees/{employee_id}",
                normalized_operation_json={"summary": "Get employee"},
                generated_tool_name="directory.get_employee",
                conflict_status="none",
                review_status="pending",
                review_notes=None,
            ),
            UpstreamServiceModel(
                id=uuid.UUID(TENANT_B_UPSTREAM_ID),
                tenant_id=uuid.UUID(TENANT_B_ID),
                namespace="hidden",
                name="hidden-api",
                description=None,
                owner="hidden-team",
                service_type="http",
                transport_type="http",
                endpoint="https://hidden.example.test",
                auth_scheme="none",
                config_json={},
                status="active",
            ),
        ]
    )
    await session.commit()


@pytest.mark.asyncio
async def test_admin_queries_cover_dashboard_catalog_execution_audit_and_tenant_boundary(
    pg_session_factory: async_sessionmaker[AsyncSession],
    migrated_database_url: str,
) -> None:
    async with pg_session_factory() as seed_session:
        await seed_admin_query_state(seed_session)
    upstream_transport = httpx.ASGITransport(app=employee_directory_app)
    async with httpx.AsyncClient(transport=upstream_transport) as upstream_client:
        app = create_app(
            Settings(
                environment="test",
                catalog_backend="postgresql",
                database_url=SecretStr(migrated_database_url),
                local_tenant_id=TENANT_A_ID,
                local_admin_principal_id="admin-query-test",
                control_plane_enabled=True,
                tool_execution_enabled=True,
            ),
            tool_http_client=upstream_client,
        )
        async with app.router.lifespan_context(app):
            transport = httpx2.ASGITransport(app=app)
            async with httpx2.AsyncClient(
                transport=transport,
                base_url="http://testserver",
            ) as client:
                mcp_transport = streamable_http_client(
                    "http://testserver/mcp",
                    http_client=client,
                )
                async with Client(mcp_transport) as mcp_client:
                    called = await mcp_client.call_tool(
                        "directory.get_employee",
                        {"employee_id": "emp-001"},
                    )
                assert called.is_error is False

                dashboard = (await client.get("/admin/dashboard")).json()
                assert dashboard == {
                    "active_upstreams": 1,
                    "published_tools": 1,
                    "pending_reviews": 1,
                    "pending_approvals": 1,
                    "failed_executions": 0,
                    "unknown_executions": 0,
                    "search_projection": {
                        "published_tools": 1,
                        "indexed_tools": 1,
                        "pending_tools": 0,
                        "coverage_percent": 100.0,
                        "embedding_model": "Qwen/Qwen3-Embedding-8B",
                        "embedding_dimensions": TOOL_EMBEDDING_DIMENSIONS,
                        "latest_indexed_at": NOW.isoformat().replace("+00:00", "Z"),
                    },
                }

                upstream = await client.get(f"/admin/upstreams/{UPSTREAM_ID}")
                assert upstream.status_code == 200
                assert upstream.json()["protocol_min"] is None
                hidden = await client.get(f"/admin/upstreams/{TENANT_B_UPSTREAM_ID}")
                assert hidden.status_code == 404
                upstream_page = await client.get(
                    "/admin/upstreams",
                    params={"namespace": "directory", "status": "active"},
                )
                assert upstream_page.json()["page"]["total"] == 1

                imports = await client.get(
                    "/admin/openapi/imports",
                    params={"status": "completed", "upstream_service_id": UPSTREAM_ID},
                )
                assert [item["id"] for item in imports.json()["items"]] == [IMPORT_ID]
                reviews = await client.get(
                    "/admin/openapi/operations",
                    params={"review_status": "pending", "conflict_status": "none"},
                )
                assert [item["id"] for item in reviews.json()["items"]] == [OPERATION_ID]

                tools = await client.get(
                    "/admin/tools",
                    params={
                        "namespace": "directory",
                        "status": "active",
                        "version_status": "published",
                        "visibility": "public",
                        "side_effect": "read_only",
                    },
                )
                assert [item["id"] for item in tools.json()["items"]] == [TOOL_ID]
                assert (await client.get(f"/admin/tools/{TOOL_ID}")).status_code == 200
                versions = await client.get(f"/admin/tools/{TOOL_ID}/versions")
                assert [item["id"] for item in versions.json()["items"]] == [VERSION_ID]
                version = await client.get(f"/admin/tool-versions/{VERSION_ID}")
                assert version.json()["tool_id"] == TOOL_ID
                assert version.json()["schema_digest"] == "1" * 64
                binding = await client.get(f"/admin/tool-bindings/{BINDING_ID}")
                assert binding.json()["binding_config"]["method"] == "GET"
                version_binding = await client.get(f"/admin/tool-versions/{VERSION_ID}/binding")
                assert version_binding.json()["id"] == BINDING_ID

                approvals = await client.get(
                    "/admin/approvals",
                    params={"status": "pending", "principal_id": "employee-agent"},
                )
                assert [item["id"] for item in approvals.json()["items"]] == [APPROVAL_ID]
                assert approvals.json()["items"][0]["has_idempotency_key"] is False

                executions = await client.get(
                    "/admin/executions",
                    params={"status": "succeeded", "tool_id": TOOL_ID},
                )
                assert executions.json()["page"]["total"] == 1
                execution = executions.json()["items"][0]
                execution_id = execution["id"]
                assert execution["has_idempotency_key"] is False
                assert execution["mcp_scope_type"] == "root"
                assert execution["toolset_id"] is None
                assert (await client.get(f"/admin/executions/{execution_id}")).status_code == 200
                attempts = await client.get(f"/admin/executions/{execution_id}/attempts")
                assert attempts.json()["items"][0]["upstream_status"] == 200

                audits = await client.get(
                    "/admin/audit-events",
                    params={
                        "trace_id": execution["trace_id"],
                        "principal_id": execution["principal_id"],
                        "tool_id": TOOL_ID,
                        "execution_id": execution_id,
                        "outcome": "succeeded",
                    },
                )
                assert audits.json()["page"]["total"] == 1
                assert '"arguments":' not in audits.text.lower()
                assert '"result":' not in audits.text.lower()
                projection = await client.get("/admin/search/projection-status")
                assert projection.json()["coverage_percent"] == 100.0

                invalid_filter = await client.get(
                    "/admin/executions",
                    params={"status": "not-a-status"},
                )
                assert invalid_filter.status_code == 422
                assert invalid_filter.json()["code"] == "request_validation_failed"
