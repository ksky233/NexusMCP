"""Static Bearer Authenticator 的 Token Digest、Tenant 与匿名行为测试。"""

import pytest

from nexusmcp.modules.credentials.domain import SecretValue
from nexusmcp.modules.identity.adapters.static_bearer import (
    StaticBearerAgentServiceAuthenticator,
    StaticBearerAgentServiceMapping,
)
from nexusmcp.modules.identity.domain import InternalPrincipal, PrincipalType
from nexusmcp.shared.errors import AuthenticationError


def _principal(tenant_id: str = "tenant-a") -> InternalPrincipal:
    return InternalPrincipal(
        id="sales-assistant-service",
        tenant_id=tenant_id,
        principal_type=PrincipalType.AGENT_SERVICE,
        authn_method="static_bearer",
    )


def test_valid_bearer_resolves_agent_service_without_retaining_raw_token() -> None:
    raw_token = "sales-assistant-super-secret-token"
    authenticator = StaticBearerAgentServiceAuthenticator(
        [StaticBearerAgentServiceMapping(SecretValue(raw_token), _principal())]
    )

    principal = authenticator.authenticate(f"Bearer {raw_token}", "tenant-a")

    assert principal.id == "sales-assistant-service"
    assert raw_token not in repr(authenticator.__dict__)


@pytest.mark.parametrize(
    "authorization",
    [
        "Basic abc",
        "Bearer unknown-token",
        "Bearer ",
    ],
)
def test_invalid_bearer_is_rejected(authorization: str) -> None:
    authenticator = StaticBearerAgentServiceAuthenticator(
        [StaticBearerAgentServiceMapping(SecretValue("valid-token"), _principal())]
    )

    with pytest.raises(AuthenticationError):
        authenticator.authenticate(authorization, "tenant-a")


def test_missing_header_and_cross_tenant_token_are_rejected() -> None:
    authenticator = StaticBearerAgentServiceAuthenticator(
        [
            StaticBearerAgentServiceMapping(
                SecretValue("tenant-b-token"),
                _principal("tenant-b"),
            )
        ]
    )

    with pytest.raises(AuthenticationError):
        authenticator.authenticate(None, "tenant-a")
    with pytest.raises(AuthenticationError):
        authenticator.authenticate("Bearer tenant-b-token", "tenant-a")
