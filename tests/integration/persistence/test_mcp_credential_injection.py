"""Modern MCP CredentialBinding → Secret Resolve → Header Injection E2E。"""

import logging

import httpx
import httpx2
import pytest
from fastapi import FastAPI, Header, HTTPException
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from nexusmcp.bootstrap.app import create_app
from nexusmcp.bootstrap.config import Settings
from nexusmcp.modules.audit.domain import AuditOutcome
from nexusmcp.modules.credentials.adapters.environment import EnvironmentCredentialProvider
from nexusmcp.modules.credentials.adapters.in_memory import (
    InMemoryCredentialBindingResolver,
)
from nexusmcp.modules.credentials.domain import (
    CredentialBinding,
    CredentialInjectionLocation,
    CredentialSubjectType,
    CredentialValueFormat,
    SecretReference,
    SecretValue,
)
from nexusmcp.modules.execution.domain import ExecutionStatus
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
from tests.contract.repositories.contracts import TENANT_A_ID, TOOL_ID, UPSTREAM_ID
from tests.integration.persistence.test_mcp_read_only_http_call import seed_executable_tool

pytestmark = pytest.mark.integration

USER_A_TOKEN = "user-a-token"
USER_B_TOKEN = "user-b-token"
UPSTREAM_SECRET = "employee-api-secret"

protected_upstream = FastAPI()


@protected_upstream.get("/employees/{employee_id}")
async def protected_employee(
    employee_id: str,
    authorization: str | None = Header(default=None),
) -> dict[str, str]:
    if authorization != f"Bearer {UPSTREAM_SECRET}":
        raise HTTPException(status_code=401)
    return {"employee_id": employee_id, "name": "Ada Chen"}


class CountingEnvironmentCredentialProvider:
    def __init__(self) -> None:
        self._provider = EnvironmentCredentialProvider({"EMPLOYEE_API_TOKEN": UPSTREAM_SECRET})
        self.calls = 0

    async def resolve(self, reference: SecretReference) -> SecretValue:
        self.calls += 1
        return await self._provider.resolve(reference)


def principal(principal_id: str, role: str) -> InternalPrincipal:
    return InternalPrincipal(
        id=principal_id,
        tenant_id=TENANT_A_ID,
        principal_type=PrincipalType.USER,
        authn_method="static_bearer",
        roles=frozenset({role}),
    )


async def call_tool(
    app: FastAPI,
    authorization: str,
):
    transport = httpx2.ASGITransport(app=app)
    async with httpx2.AsyncClient(
        transport=transport,
        base_url="http://testserver",
        headers={"Authorization": authorization},
    ) as http_client:
        mcp_transport = streamable_http_client(
            "http://testserver/mcp",
            http_client=http_client,
        )
        async with Client(mcp_transport) as client:
            return await client.call_tool(
                "directory.get_employee",
                {"employee_id": "emp-001"},
            )


@pytest.mark.asyncio
async def test_allow_injects_secret_while_deny_never_resolves_it(
    pg_session_factory: async_sessionmaker[AsyncSession],
    migrated_database_url: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    async with pg_session_factory() as seed_session:
        await seed_executable_tool(seed_session, auth_scheme="bearer")
    authenticator = StaticBearerPrincipalAuthenticator(
        [
            StaticBearerIdentity(
                SecretValue(USER_A_TOKEN),
                principal("user-a", "employee_reader"),
            ),
            StaticBearerIdentity(
                SecretValue(USER_B_TOKEN),
                principal("user-b", "inventory_operator"),
            ),
        ]
    )
    policy = RuleBasedPolicyEvaluator(
        [
            ToolPolicy(
                id="allow-user-a",
                tenant_id=TENANT_A_ID,
                subject_type=PolicySubjectType.PRINCIPAL,
                subject_id="user-a",
                tool_id=TOOL_ID,
                action=ToolAction.CALL,
                effect=PolicyEffect.ALLOW,
                priority=10,
                version="policy-v1",
                reason_code="employee_reader_allowed",
            ),
            ToolPolicy(
                id="deny-user-b",
                tenant_id=TENANT_A_ID,
                subject_type=PolicySubjectType.PRINCIPAL,
                subject_id="user-b",
                tool_id=TOOL_ID,
                action=ToolAction.CALL,
                effect=PolicyEffect.DENY,
                priority=10,
                version="policy-v1",
                reason_code="inventory_operator_denied",
            ),
        ]
    )
    binding = CredentialBinding(
        id="credential-binding-user-a",
        tenant_id=TENANT_A_ID,
        subject_type=CredentialSubjectType.PRINCIPAL,
        subject_id="user-a",
        tool_id=TOOL_ID,
        upstream_service_id=UPSTREAM_ID,
        secret_reference=SecretReference(
            provider="environment",
            reference="EMPLOYEE_API_TOKEN",
        ),
        injection_location=CredentialInjectionLocation.HEADER,
        injection_name="Authorization",
        value_format=CredentialValueFormat.BEARER,
    )
    provider = CountingEnvironmentCredentialProvider()
    upstream_transport = httpx.ASGITransport(app=protected_upstream)
    caplog.set_level(logging.INFO, logger="nexusmcp")

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
            policy_evaluator=policy,
            credential_binding_resolver=InMemoryCredentialBindingResolver([binding]),
            credential_provider=provider,
        )
        async with app.router.lifespan_context(app):
            allowed = await call_tool(app, f"Bearer {USER_A_TOKEN}")
            denied = await call_tool(app, f"Bearer {USER_B_TOKEN}")
            execution_reader = app.state.execution_reader
            audit_reader = app.state.audit_reader
            executions = await execution_reader.list_by_tenant(TENANT_A_ID)
            audits = await audit_reader.list_by_tenant(TENANT_A_ID)

    assert allowed.is_error is False
    assert allowed.structured_content == {"employee_id": "emp-001", "name": "Ada Chen"}
    assert denied.is_error is True
    assert denied.meta is not None
    assert denied.meta["com.nexusmcp/errorCode"] == "authorization_denied"
    # 第二次调用被 Policy 拒绝，不能进入 Credential Resolver/Provider。
    assert provider.calls == 1
    assert len(executions) == 1
    assert executions[0].status is ExecutionStatus.SUCCEEDED
    assert executions[0].credential_binding_id == "credential-binding-user-a"
    assert [event.outcome for event in audits] == [
        AuditOutcome.ALLOWED,
        AuditOutcome.SUCCEEDED,
        AuditOutcome.DENIED,
    ]
    assert UPSTREAM_SECRET not in repr(executions[0])
    assert UPSTREAM_SECRET not in repr(audits)
    assert UPSTREAM_SECRET not in repr(allowed)
    assert UPSTREAM_SECRET not in caplog.text
