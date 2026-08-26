"""Internal Principal 信任事实测试。"""

import pytest

from nexusmcp.modules.identity.domain import InternalPrincipal, PrincipalType


def test_anonymous_principal_cannot_carry_trusted_roles() -> None:
    with pytest.raises(ValueError, match="anonymous"):
        InternalPrincipal(
            id="anonymous",
            tenant_id="tenant-a",
            principal_type=PrincipalType.ANONYMOUS,
            authn_method="none",
            roles=frozenset({"admin"}),
        )


def test_internal_principal_contains_no_raw_token_field() -> None:
    principal = InternalPrincipal(
        id="user-a",
        tenant_id="tenant-a",
        principal_type=PrincipalType.USER,
        authn_method="jwt",
        roles=frozenset({"operator"}),
        attributes={"department": "operations"},
    )

    assert principal.roles == frozenset({"operator"})
    assert "token" not in principal.__dataclass_fields__
