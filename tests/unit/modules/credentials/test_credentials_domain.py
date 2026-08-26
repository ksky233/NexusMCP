"""SecretReference、SecretValue 与 Binding Scope 测试。"""

import pytest

from nexusmcp.modules.credentials.domain import (
    CredentialBinding,
    CredentialInjectionLocation,
    CredentialSubjectType,
    CredentialValueFormat,
    SecretReference,
    SecretValue,
)


def test_secret_value_never_reveals_itself_in_string_representation() -> None:
    secret = SecretValue("super-secret-token")

    assert str(secret) == "[REDACTED]"
    assert "super-secret-token" not in repr(secret)
    assert secret.reveal() == "super-secret-token"


def test_secret_reference_separates_provider_and_opaque_reference() -> None:
    reference = SecretReference(
        provider="environment",
        reference="INVENTORY_API_KEY",
    )

    assert reference.provider == "environment"
    with pytest.raises(ValueError, match="opaque"):
        SecretReference(provider="environment", reference="env://INVENTORY_API_KEY")


def test_credential_binding_enforces_subject_scope() -> None:
    with pytest.raises(ValueError, match="subject id"):
        CredentialBinding(
            id="binding-1",
            tenant_id="tenant-a",
            subject_type=CredentialSubjectType.PRINCIPAL,
            subject_id=None,
            tool_id="tool-1",
            upstream_service_id="upstream-1",
            secret_reference=SecretReference(
                provider="environment",
                reference="API_KEY",
            ),
            injection_location=CredentialInjectionLocation.HEADER,
            injection_name="Authorization",
            value_format=CredentialValueFormat.BEARER,
        )
