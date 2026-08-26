"""同一 Modern MCP Tool 对不同 Principal 执行 ALLOW/DENY 的 E2E。"""

import httpx
import httpx2
import pytest
from fastapi import FastAPI
from mcp import Client, types
from mcp.client.streamable_http import streamable_http_client
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from examples.upstream_apis.employee_directory.app import app as employee_directory_app
from nexusmcp.bootstrap.app import create_app
from nexusmcp.bootstrap.config import Settings
from nexusmcp.modules.audit.domain import AuditOutcome
from nexusmcp.modules.credentials.domain import SecretValue
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

USER_A_TOKEN = "user-a-token"
USER_B_TOKEN = "user-b-token"


def internal_principal(
    principal_id: str,
    role: str,
) -> InternalPrincipal:
    return InternalPrincipal(
        id=principal_id,
        tenant_id=TENANT_A_ID,
        principal_type=PrincipalType.USER,
        authn_method="static_bearer",
        roles=frozenset({role}),
    )


def policies() -> tuple[ToolPolicy, ...]:
    return (
        ToolPolicy(
            id="employee-reader-allow",
            tenant_id=TENANT_A_ID,
            subject_type=PolicySubjectType.ROLE,
            subject_id="employee_reader",
            tool_id=TOOL_ID,
            action=ToolAction.CALL,
            effect=PolicyEffect.ALLOW,
            priority=10,
            version="policy-v1",
            reason_code="employee_reader_allowed",
        ),
        ToolPolicy(
            id="inventory-operator-deny",
            tenant_id=TENANT_A_ID,
            subject_type=PolicySubjectType.ROLE,
            subject_id="inventory_operator",
            tool_id=TOOL_ID,
            action=ToolAction.CALL,
            effect=PolicyEffect.DENY,
            priority=10,
            version="policy-v1",
            reason_code="inventory_operator_denied",
        ),
    )


async def call_with_authorization(
    app: FastAPI,
    authorization: str | None,
    *,
    list_before_call: bool = False,
) -> tuple[types.ListToolsResult | None, types.CallToolResult]:
    transport = httpx2.ASGITransport(app=app)
    headers = {"Authorization": authorization} if authorization is not None else {}
    async with httpx2.AsyncClient(
        transport=transport,
        base_url="http://testserver",
        headers=headers,
    ) as http_client:
        mcp_transport = streamable_http_client(
            "http://testserver/mcp",
            http_client=http_client,
        )
        async with Client(mcp_transport) as client:
            listed = await client.list_tools(cache_mode="refresh") if list_before_call else None
            result = await client.call_tool(
                "directory.get_employee",
                {"employee_id": "emp-001"},
            )
            return listed, result


@pytest.mark.asyncio
async def test_same_tool_is_allowed_denied_or_unauthenticated_by_principal(
    pg_session_factory: async_sessionmaker[AsyncSession],
    migrated_database_url: str,
) -> None:
    async with pg_session_factory() as seed_session:
        await seed_executable_tool(seed_session)
    authenticator = StaticBearerPrincipalAuthenticator(
        [
            StaticBearerIdentity(
                SecretValue(USER_A_TOKEN),
                internal_principal("user-a", "employee_reader"),
            ),
            StaticBearerIdentity(
                SecretValue(USER_B_TOKEN),
                internal_principal("user-b", "inventory_operator"),
            ),
        ]
    )
    upstream_transport = httpx.ASGITransport(app=employee_directory_app)
    async with httpx.AsyncClient(transport=upstream_transport) as upstream_client:
        app = create_app(
            Settings(
                environment="test",
                catalog_backend="postgresql",
                database_url=SecretStr(migrated_database_url),
                local_tenant_id=TENANT_A_ID,
                tool_execution_enabled=True,
            ),
            tool_http_client=upstream_client,
            principal_authenticator=authenticator,
            policy_evaluator=RuleBasedPolicyEvaluator(policies()),
        )
        async with app.router.lifespan_context(app):
            user_a_list, user_a = await call_with_authorization(
                app,
                f"Bearer {USER_A_TOKEN}",
                list_before_call=True,
            )
            user_b_list, user_b = await call_with_authorization(
                app,
                f"Bearer {USER_B_TOKEN}",
                list_before_call=True,
            )
            _unknown_list, unknown = await call_with_authorization(
                app,
                "Bearer unknown-token",
            )
            _anonymous_list, anonymous = await call_with_authorization(app, None)
            execution_reader = app.state.execution_reader
            audit_reader = app.state.audit_reader
            executions = await execution_reader.list_by_tenant(TENANT_A_ID)
            audits = await audit_reader.list_by_tenant(TENANT_A_ID)

    assert user_a_list is not None
    assert [tool.name for tool in user_a_list.tools] == ["directory.get_employee"]
    assert user_a.is_error is False
    assert user_b_list is not None
    # tools/list 可见不代表 tools/call 被授权，调用阶段必须重新执行 Policy。
    assert [tool.name for tool in user_b_list.tools] == ["directory.get_employee"]
    assert user_b.is_error is True
    assert user_b.meta is not None
    assert user_b.meta["com.nexusmcp/errorCode"] == "authorization_denied"
    assert unknown.is_error is True
    assert unknown.meta is not None
    assert unknown.meta["com.nexusmcp/errorCode"] == "authentication_failed"
    assert anonymous.is_error is True
    assert anonymous.meta is not None
    assert anonymous.meta["com.nexusmcp/errorCode"] == "authorization_denied"
    assert len(executions) == 1
    assert executions[0].principal_id == "user-a"
    assert [event.outcome for event in audits] == [
        AuditOutcome.ALLOWED,
        AuditOutcome.SUCCEEDED,
        AuditOutcome.DENIED,
        AuditOutcome.DENIED,
    ]
