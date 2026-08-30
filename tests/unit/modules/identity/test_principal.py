"""Internal Principal 信任事实测试。"""

from nexusmcp.modules.identity.domain import InternalPrincipal, PrincipalType


def test_anonymous_principal_contains_only_protocol_trust_facts() -> None:
    principal = InternalPrincipal(
        id="anonymous",
        tenant_id="tenant-a",
        principal_type=PrincipalType.ANONYMOUS,
        authn_method="none",
    )

    assert principal.principal_type is PrincipalType.ANONYMOUS


def test_internal_principal_contains_no_raw_token_field() -> None:
    principal = InternalPrincipal(
        id="sales-assistant-service",
        tenant_id="tenant-a",
        principal_type=PrincipalType.AGENT_SERVICE,
        authn_method="static_bearer",
    )

    assert "token" not in principal.__dataclass_fields__
    assert "roles" not in principal.__dataclass_fields__
    assert "attributes" not in principal.__dataclass_fields__
