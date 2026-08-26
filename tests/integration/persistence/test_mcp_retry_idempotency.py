"""Modern MCP 幂等 PUT、Transient Retry 与 Duplicate Key E2E。"""

import json
import uuid
from datetime import UTC, datetime

import httpx
import httpx2
import pytest
from mcp import Client, types
from mcp.client.streamable_http import streamable_http_client
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from nexusmcp.bootstrap.app import create_app
from nexusmcp.bootstrap.config import Settings
from nexusmcp.modules.catalog.adapters.sqlalchemy_models import ToolModel, ToolVersionModel
from nexusmcp.modules.connectors.adapters.sqlalchemy_models import ToolBindingModel
from nexusmcp.modules.credentials.domain import SecretValue
from nexusmcp.modules.execution.domain import ExecutionAttemptStatus, ExecutionStatus
from nexusmcp.modules.identity.adapters.sqlalchemy_models import TenantModel
from nexusmcp.modules.identity.adapters.static_bearer import (
    StaticBearerIdentity,
    StaticBearerPrincipalAuthenticator,
)
from nexusmcp.modules.identity.domain import InternalPrincipal, PrincipalType
from nexusmcp.modules.policy.adapters.rule_based import RuleBasedPolicyEvaluator
from nexusmcp.modules.policy.domain import (
    PolicyEffect,
    PolicySubjectType,
    ToolAction,
    ToolPolicy,
)
from nexusmcp.modules.registry.adapters.sqlalchemy_models import UpstreamServiceModel
from tests.contract.repositories.contracts import TENANT_A_ID

pytestmark = pytest.mark.integration

TOOL_ID = "00000000-0000-0000-0000-000000000071"
VERSION_ID = "00000000-0000-0000-0000-000000000072"
BINDING_ID = "00000000-0000-0000-0000-000000000073"
UPSTREAM_ID = "00000000-0000-0000-0000-000000000074"
USER_TOKEN = "inventory-writer-token"
IDEMPOTENCY_META_KEY = "com.nexusmcp/idempotencyKey"


async def seed_idempotent_inventory_tool(session: AsyncSession) -> None:
    tenant_id = uuid.UUID(TENANT_A_ID)
    now = datetime(2026, 8, 26, 23, 45, tzinfo=UTC)
    session.add(TenantModel(id=tenant_id, name="Retry Tenant", status="active"))
    await session.flush()
    session.add(
        UpstreamServiceModel(
            id=uuid.UUID(UPSTREAM_ID),
            tenant_id=tenant_id,
            namespace="inventory",
            name="inventory-retry-api",
            description="Idempotent inventory demo",
            owner="retry-test",
            service_type="http",
            transport_type="http",
            endpoint="http://inventory.test",
            auth_scheme="none",
            config_json={},
            status="active",
        )
    )
    session.add(
        ToolModel(
            id=uuid.UUID(TOOL_ID),
            tenant_id=tenant_id,
            namespace="inventory",
            canonical_name="inventory.set_reorder_level",
            owner="retry-test",
            status="active",
        )
    )
    await session.flush()
    session.add(
        ToolVersionModel(
            id=uuid.UUID(VERSION_ID),
            tenant_id=tenant_id,
            tool_id=uuid.UUID(TOOL_ID),
            version=1,
            display_name="Set reorder level",
            description="Set one idempotent inventory reorder level.",
            input_schema_json={
                "type": "object",
                "properties": {
                    "sku": {"type": "string", "minLength": 1},
                    "body": {
                        "type": "object",
                        "properties": {
                            "warehouse_id": {"type": "string", "minLength": 1},
                            "reorder_level": {
                                "type": "integer",
                                "minimum": 0,
                                "maximum": 1000,
                            },
                        },
                        "required": ["warehouse_id", "reorder_level"],
                        "additionalProperties": False,
                    },
                },
                "required": ["sku", "body"],
                "additionalProperties": False,
            },
            output_schema_json=None,
            schema_digest="7" * 64,
            tags_json=["inventory", "write", "idempotent"],
            search_name="inventory inventory.set_reorder_level Set reorder level",
            search_tags="inventory write idempotent",
            search_description="Set one idempotent inventory reorder level.",
            side_effect="idempotent_write",
            visibility="authenticated",
            status="published",
            created_by="retry-test",
            created_at=now,
            reviewed_at=now,
            published_at=now,
        )
    )
    await session.flush()
    session.add(
        ToolBindingModel(
            id=uuid.UUID(BINDING_ID),
            tenant_id=tenant_id,
            tool_version_id=uuid.UUID(VERSION_ID),
            upstream_service_id=uuid.UUID(UPSTREAM_ID),
            imported_operation_id=None,
            binding_type="http",
            binding_config_json={
                "method": "PUT",
                "path_template": "/inventory/{sku}/reorder-level",
                "parameters": [
                    {
                        "argument_name": "sku",
                        "upstream_name": "sku",
                        "location": "path",
                        "required": True,
                    }
                ],
                "request_body": {
                    "argument_name": "body",
                    "content_type": "application/json",
                    "required": True,
                },
            },
            binding_digest="8" * 64,
            status="published",
            published_at=now,
        )
    )
    await session.commit()


def authenticator() -> StaticBearerPrincipalAuthenticator:
    return StaticBearerPrincipalAuthenticator(
        [
            StaticBearerIdentity(
                SecretValue(USER_TOKEN),
                InternalPrincipal(
                    id="inventory-writer",
                    tenant_id=TENANT_A_ID,
                    principal_type=PrincipalType.USER,
                    authn_method="static_bearer",
                    roles=frozenset({"inventory_writer"}),
                ),
            )
        ]
    )


def policy() -> RuleBasedPolicyEvaluator:
    return RuleBasedPolicyEvaluator(
        [
            ToolPolicy(
                id="inventory-writer-allow",
                tenant_id=TENANT_A_ID,
                subject_type=PolicySubjectType.ROLE,
                subject_id="inventory_writer",
                tool_id=TOOL_ID,
                action=ToolAction.CALL,
                effect=PolicyEffect.ALLOW,
                priority=10,
                version="policy-v1",
                reason_code="inventory_writer_allowed",
            )
        ]
    )


def arguments(reorder_level: int) -> dict[str, object]:
    return {
        "sku": "laptop-pro-14",
        "body": {"warehouse_id": "shanghai-01", "reorder_level": reorder_level},
    }


@pytest.mark.asyncio
async def test_idempotent_put_retries_then_rejects_duplicate_and_conflicting_keys(
    pg_session_factory: async_sessionmaker[AsyncSession],
    migrated_database_url: str,
) -> None:
    async with pg_session_factory() as seed_session:
        await seed_idempotent_inventory_tool(seed_session)
    upstream_requests: list[httpx.Request] = []

    def upstream_handler(request: httpx.Request) -> httpx.Response:
        upstream_requests.append(request)
        if len(upstream_requests) <= 2:
            return httpx.Response(503, json={"error": "transient"})
        body = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "sku": "laptop-pro-14",
                "warehouse_id": body["warehouse_id"],
                "reorder_level": body["reorder_level"],
            },
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(upstream_handler)
    ) as upstream_client:
        app = create_app(
            Settings(
                environment="test",
                catalog_backend="postgresql",
                database_url=SecretStr(migrated_database_url),
                local_tenant_id=TENANT_A_ID,
                tool_execution_enabled=True,
                tool_retry_max_attempts=3,
                tool_retry_initial_backoff_seconds=0,
            ),
            tool_http_client=upstream_client,
            principal_authenticator=authenticator(),
            policy_evaluator=policy(),
        )
        async with app.router.lifespan_context(app):
            transport = httpx2.ASGITransport(app=app)
            async with httpx2.AsyncClient(
                transport=transport,
                base_url="http://testserver",
                headers={"Authorization": f"Bearer {USER_TOKEN}"},
            ) as http_client:
                mcp_transport = streamable_http_client(
                    "http://testserver/mcp",
                    http_client=http_client,
                )
                async with Client(mcp_transport) as client:
                    metadata: types.RequestParamsMeta = {IDEMPOTENCY_META_KEY: "reorder-write-001"}
                    success = await client.call_tool(
                        "inventory.set_reorder_level",
                        arguments(12),
                        meta=metadata,
                    )
                    duplicate = await client.call_tool(
                        "inventory.set_reorder_level",
                        arguments(12),
                        meta=metadata,
                    )
                    conflict = await client.call_tool(
                        "inventory.set_reorder_level",
                        arguments(20),
                        meta=metadata,
                    )
                    missing_key = await client.call_tool(
                        "inventory.set_reorder_level",
                        arguments(12),
                    )
            execution_reader = app.state.execution_reader
            executions = await execution_reader.list_by_tenant(TENANT_A_ID)
            attempts = await execution_reader.list_attempts(
                TENANT_A_ID,
                executions[0].id,
            )

    assert success.is_error is False
    assert success.structured_content["reorder_level"] == 12
    assert success.meta is not None
    assert success.meta["com.nexusmcp/attemptCount"] == 3
    assert duplicate.is_error is True
    assert duplicate.meta is not None
    assert duplicate.meta["com.nexusmcp/errorCode"] == "idempotency_already_completed"
    assert duplicate.meta["com.nexusmcp/existingExecutionId"] == executions[0].id
    assert conflict.is_error is True
    assert conflict.meta is not None
    assert conflict.meta["com.nexusmcp/errorCode"] == "idempotency_conflict"
    assert missing_key.is_error is True
    assert missing_key.meta is not None
    assert missing_key.meta["com.nexusmcp/errorCode"] == "idempotency_key_required"
    assert len(upstream_requests) == 3
    assert {request.headers["Idempotency-Key"] for request in upstream_requests} == {
        "reorder-write-001"
    }
    assert len(executions) == 1
    assert executions[0].status is ExecutionStatus.SUCCEEDED
    assert executions[0].attempt_count == 3
    assert [attempt.status for attempt in attempts] == [
        ExecutionAttemptStatus.FAILED,
        ExecutionAttemptStatus.FAILED,
        ExecutionAttemptStatus.SUCCEEDED,
    ]
