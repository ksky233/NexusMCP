"""Credential Binding 的特异性选择、禁用与冲突测试。"""

import pytest

from nexusmcp.modules.credentials.adapters.in_memory import (
    InMemoryCredentialBindingResolver,
)
from nexusmcp.modules.credentials.domain import (
    CredentialBinding,
    CredentialBindingStatus,
    CredentialInjectionLocation,
    CredentialSubjectType,
    CredentialValueFormat,
    SecretReference,
)
from nexusmcp.modules.identity.domain import InternalPrincipal, PrincipalType
from nexusmcp.shared.errors import (
    CredentialBindingConflictError,
    TenantBoundaryViolationError,
)


def principal(*, tenant_id: str = "tenant-a") -> InternalPrincipal:
    return InternalPrincipal(
        id="user-a",
        tenant_id=tenant_id,
        principal_type=PrincipalType.USER,
        authn_method="test",
        roles=frozenset({"employee_reader"}),
    )


def binding(
    binding_id: str,
    subject_type: CredentialSubjectType,
    subject_id: str | None,
    *,
    tool_id: str | None = "tool-1",
    status: CredentialBindingStatus = CredentialBindingStatus.ACTIVE,
) -> CredentialBinding:
    return CredentialBinding(
        id=binding_id,
        tenant_id="tenant-a",
        subject_type=subject_type,
        subject_id=subject_id,
        tool_id=tool_id,
        upstream_service_id="upstream-1",
        secret_reference=SecretReference(
            provider="environment",
            reference=f"{binding_id.upper().replace('-', '_')}_TOKEN",
        ),
        injection_location=CredentialInjectionLocation.HEADER,
        injection_name="Authorization",
        value_format=CredentialValueFormat.BEARER,
        status=status,
    )


@pytest.mark.asyncio
async def test_principal_exact_tool_binding_outranks_role_and_tenant() -> None:
    resolver = InMemoryCredentialBindingResolver(
        [
            binding("tenant", CredentialSubjectType.TENANT, None),
            binding("role", CredentialSubjectType.ROLE, "employee_reader"),
            binding("principal", CredentialSubjectType.PRINCIPAL, "user-a"),
        ]
    )

    resolved = await resolver.resolve("tenant-a", principal(), "tool-1", "upstream-1")

    assert resolved is not None and resolved.id == "principal"


@pytest.mark.asyncio
async def test_exact_tool_binding_outranks_subject_wildcard_and_disabled_is_ignored() -> None:
    resolver = InMemoryCredentialBindingResolver(
        [
            binding("wildcard", CredentialSubjectType.ROLE, "employee_reader", tool_id=None),
            binding("exact", CredentialSubjectType.ROLE, "employee_reader"),
            binding(
                "disabled-principal",
                CredentialSubjectType.PRINCIPAL,
                "user-a",
                status=CredentialBindingStatus.DISABLED,
            ),
        ]
    )

    resolved = await resolver.resolve("tenant-a", principal(), "tool-1", "upstream-1")

    assert resolved is not None and resolved.id == "exact"


@pytest.mark.asyncio
async def test_same_specificity_bindings_fail_closed() -> None:
    resolver = InMemoryCredentialBindingResolver(
        [
            binding("first", CredentialSubjectType.PRINCIPAL, "user-a"),
            binding("second", CredentialSubjectType.PRINCIPAL, "user-a"),
        ]
    )

    with pytest.raises(CredentialBindingConflictError):
        await resolver.resolve("tenant-a", principal(), "tool-1", "upstream-1")


@pytest.mark.asyncio
async def test_principal_cannot_cross_credential_tenant_boundary() -> None:
    resolver = InMemoryCredentialBindingResolver([])

    with pytest.raises(TenantBoundaryViolationError):
        await resolver.resolve("tenant-a", principal(tenant_id="tenant-b"), "tool-1", "upstream-1")
