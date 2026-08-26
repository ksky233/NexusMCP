"""Static Bearer Authenticator 的 Token Digest、Tenant 与匿名行为测试。"""

import pytest

from nexusmcp.modules.credentials.domain import SecretValue
from nexusmcp.modules.identity.adapters.static_bearer import (
    StaticBearerIdentity,
    StaticBearerPrincipalAuthenticator,
)
from nexusmcp.modules.identity.domain import InternalPrincipal, PrincipalType
from nexusmcp.shared.errors import AuthenticationError


def _principal(tenant_id: str = "tenant-a") -> InternalPrincipal:
    return InternalPrincipal(
        id="user-a",
        tenant_id=tenant_id,
        principal_type=PrincipalType.USER,
        authn_method="static_bearer",
        roles=frozenset({"employee_reader"}),
    )


def test_valid_bearer_resolves_roles_without_retaining_raw_token() -> None:
    raw_token = "user-a-super-secret-token"
    authenticator = StaticBearerPrincipalAuthenticator(
        [StaticBearerIdentity(SecretValue(raw_token), _principal())]
    )

    principal = authenticator.authenticate(f"Bearer {raw_token}", "tenant-a")

    assert principal.roles == frozenset({"employee_reader"})
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
    authenticator = StaticBearerPrincipalAuthenticator(
        [StaticBearerIdentity(SecretValue("valid-token"), _principal())]
    )

    with pytest.raises(AuthenticationError):
        authenticator.authenticate(authorization, "tenant-a")


def test_missing_header_can_resolve_anonymous_but_cross_tenant_token_cannot() -> None:
    authenticator = StaticBearerPrincipalAuthenticator(
        [StaticBearerIdentity(SecretValue("tenant-b-token"), _principal("tenant-b"))]
    )

    anonymous = authenticator.authenticate(None, "tenant-a")
    assert anonymous.principal_type is PrincipalType.ANONYMOUS
    with pytest.raises(AuthenticationError):
        authenticator.authenticate("Bearer tenant-b-token", "tenant-a")
