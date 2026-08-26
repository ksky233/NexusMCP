"""Modern MCP MRTR 与 Control Plane 异步 Approval 恢复 E2E。"""

import httpx
import httpx2
import pytest
from mcp import Client, types
from mcp.client.session import ClientRequestContext
from mcp.client.streamable_http import streamable_http_client
from mcp.shared.exceptions import MCPError
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from examples.upstream_apis.employee_directory.app import app as employee_directory_app
from nexusmcp.bootstrap.app import create_app
from nexusmcp.bootstrap.config import Settings
from nexusmcp.modules.approval.adapters.sqlalchemy_models import ApprovalRequestModel
from nexusmcp.modules.credentials.domain import SecretValue
from nexusmcp.modules.execution.adapters.in_memory import InMemoryToolExecutionRepository
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
from tests.contract.repositories.contracts import TENANT_A_ID, TOOL_ID
from tests.integration.persistence.test_mcp_read_only_http_call import seed_executable_tool

pytestmark = pytest.mark.integration

USER_TOKEN = "approval-user-token"
APPROVAL_ID_META_KEY = "com.nexusmcp/approvalId"
REQUEST_STATE_KEY = "nexusmcp-request-state-test-key-2026"


def authenticator() -> StaticBearerPrincipalAuthenticator:
    return StaticBearerPrincipalAuthenticator(
        [
            StaticBearerIdentity(
                SecretValue(USER_TOKEN),
                InternalPrincipal(
                    id="user-approval",
                    tenant_id=TENANT_A_ID,
                    principal_type=PrincipalType.USER,
                    authn_method="static_bearer",
                    roles=frozenset({"approval_required"}),
                ),
            )
        ]
    )


def approval_policy() -> RuleBasedPolicyEvaluator:
    return RuleBasedPolicyEvaluator(
        [
            ToolPolicy(
                id="employee-call-requires-approval",
                tenant_id=TENANT_A_ID,
                subject_type=PolicySubjectType.ROLE,
                subject_id="approval_required",
                tool_id=TOOL_ID,
                action=ToolAction.CALL,
                effect=PolicyEffect.REQUIRE_APPROVAL,
                priority=10,
                version="policy-v1",
                reason_code="human_confirmation_required",
            )
        ]
    )


def settings(database_url: str, *, control_plane: bool = False) -> Settings:
    return Settings(
        environment="test",
        catalog_backend="postgresql",
        database_url=SecretStr(database_url),
        local_tenant_id=TENANT_A_ID,
        tool_execution_enabled=True,
        control_plane_enabled=control_plane,
        local_admin_principal_id="admin-approver",
        request_state_key=SecretStr(REQUEST_STATE_KEY),
    )


async def consumed_approvals(
    session_factory: async_sessionmaker[AsyncSession],
) -> list[ApprovalRequestModel]:
    async with session_factory() as session:
        return list(
            await session.scalars(
                select(ApprovalRequestModel).order_by(ApprovalRequestModel.requested_at)
            )
        )


@pytest.mark.asyncio
async def test_modern_mrtr_elicitation_approves_and_resumes_tool_call(
    pg_session_factory: async_sessionmaker[AsyncSession],
    migrated_database_url: str,
) -> None:
    async with pg_session_factory() as seed_session:
        await seed_executable_tool(seed_session)
    callback_calls = 0

    async def approve_in_host(
        context: ClientRequestContext,
        params: types.ElicitRequestParams,
    ) -> types.ElicitResult:
        nonlocal callback_calls
        _ = context
        callback_calls += 1
        assert isinstance(params, types.ElicitRequestFormParams)
        assert "directory.get_employee" in params.message
        return types.ElicitResult(action="accept", content={"approved": True})

    upstream_transport = httpx.ASGITransport(app=employee_directory_app)
    async with httpx.AsyncClient(transport=upstream_transport) as upstream_client:
        app = create_app(
            settings(migrated_database_url),
            tool_http_client=upstream_client,
            principal_authenticator=authenticator(),
            policy_evaluator=approval_policy(),
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
                async with Client(
                    mcp_transport,
                    elicitation_callback=approve_in_host,
                ) as client:
                    result = await client.call_tool(
                        "directory.get_employee",
                        {"employee_id": "emp-001"},
                    )

    approvals = await consumed_approvals(pg_session_factory)
    assert result.is_error is False
    assert result.structured_content["name"] == "Ada Chen"
    assert callback_calls == 1
    assert len(approvals) == 1
    assert approvals[0].status == "consumed"
    assert approvals[0].decided_by == "user-approval"


@pytest.mark.asyncio
async def test_modern_mrtr_decline_rejects_without_creating_execution(
    pg_session_factory: async_sessionmaker[AsyncSession],
    migrated_database_url: str,
) -> None:
    async with pg_session_factory() as seed_session:
        await seed_executable_tool(seed_session)

    async def decline_in_host(
        context: ClientRequestContext,
        params: types.ElicitRequestParams,
    ) -> types.ElicitResult:
        _ = (context, params)
        return types.ElicitResult(action="decline")

    upstream_transport = httpx.ASGITransport(app=employee_directory_app)
    async with httpx.AsyncClient(transport=upstream_transport) as upstream_client:
        app = create_app(
            settings(migrated_database_url),
            tool_http_client=upstream_client,
            principal_authenticator=authenticator(),
            policy_evaluator=approval_policy(),
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
                async with Client(
                    mcp_transport,
                    elicitation_callback=decline_in_host,
                ) as client:
                    result = await client.call_tool(
                        "directory.get_employee",
                        {"employee_id": "emp-001"},
                    )
        execution_repository = app.state.execution_repository

    approvals = await consumed_approvals(pg_session_factory)
    assert result.is_error is True
    assert result.meta is not None
    assert result.meta["com.nexusmcp/errorCode"] == "approval_rejected"
    assert len(approvals) == 1 and approvals[0].status == "rejected"
    assert isinstance(execution_repository, InMemoryToolExecutionRepository)
    assert await execution_repository.list_by_tenant(TENANT_A_ID) == ()


@pytest.mark.asyncio
async def test_control_plane_approval_resumes_later_and_replay_is_rejected(
    pg_session_factory: async_sessionmaker[AsyncSession],
    migrated_database_url: str,
) -> None:
    async with pg_session_factory() as seed_session:
        await seed_executable_tool(seed_session)
    upstream_transport = httpx.ASGITransport(app=employee_directory_app)
    async with httpx.AsyncClient(transport=upstream_transport) as upstream_client:
        first_app = create_app(
            settings(migrated_database_url),
            tool_http_client=upstream_client,
            principal_authenticator=authenticator(),
            policy_evaluator=approval_policy(),
        )
        async with first_app.router.lifespan_context(first_app):
            transport = httpx2.ASGITransport(app=first_app)
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
                    first = await client.session.call_tool(
                        "directory.get_employee",
                        {"employee_id": "emp-001"},
                        allow_input_required=True,
                    )
                    assert isinstance(first, types.InputRequiredResult)
                    assert first.meta is not None
                    approval_id = first.meta[APPROVAL_ID_META_KEY]
                    request_state = first.request_state
                    assert isinstance(approval_id, str)
                    assert request_state is not None and request_state != approval_id

                    tampered_state = request_state[:-1] + ("A" if request_state[-1] != "A" else "B")
                    with pytest.raises(MCPError):
                        await client.session.call_tool(
                            "directory.get_employee",
                            {"employee_id": "emp-001"},
                            request_state=tampered_state,
                            allow_input_required=True,
                        )

                    # requestState 同时绑定 Tool 与 Arguments，篡改参数不能借用原审批。
                    with pytest.raises(MCPError):
                        await client.session.call_tool(
                            "directory.get_employee",
                            {"employee_id": "emp-002"},
                            request_state=request_state,
                            allow_input_required=True,
                        )

        # 第一轮进程已结束；共享 requestState Key + PostgreSQL Approval 支持稍后恢复。
        resumed_app = create_app(
            settings(migrated_database_url, control_plane=True),
            tool_http_client=upstream_client,
            principal_authenticator=authenticator(),
            policy_evaluator=approval_policy(),
        )
        async with resumed_app.router.lifespan_context(resumed_app):
            transport = httpx2.ASGITransport(app=resumed_app)
            async with httpx2.AsyncClient(
                transport=transport,
                base_url="http://testserver",
                headers={"Authorization": f"Bearer {USER_TOKEN}"},
            ) as http_client:
                pending = await http_client.get(f"/admin/approvals/{approval_id}")
                approved = await http_client.post(f"/admin/approvals/{approval_id}/approve")
                mcp_transport = streamable_http_client(
                    "http://testserver/mcp",
                    http_client=http_client,
                )
                async with Client(mcp_transport) as client:
                    resumed = await client.call_tool(
                        "directory.get_employee",
                        {"employee_id": "emp-001"},
                        request_state=request_state,
                    )
                    replayed = await client.call_tool(
                        "directory.get_employee",
                        {"employee_id": "emp-001"},
                        request_state=request_state,
                    )

    assert pending.status_code == 200
    assert pending.json()["status"] == "pending"
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"
    assert approved.json()["decided_by"] == "admin-approver"
    assert resumed.is_error is False
    assert replayed.is_error is True
    assert replayed.meta is not None
    assert replayed.meta["com.nexusmcp/errorCode"] == "approval_already_consumed"
    approvals = await consumed_approvals(pg_session_factory)
    assert len(approvals) == 1
    assert approvals[0].status == "consumed"
